from __future__ import annotations

import json
import re
from typing import Any

from . import ai_batch_service, drawing_vision

_ORIGINAL_OVERVIEW_PROMPT = drawing_vision._overview_prompt
_ORIGINAL_TILE_PROMPT = drawing_vision._tile_prompt
_ORIGINAL_VISION_REQUEST = drawing_vision._vision_request
_ORIGINAL_ANALYZE = drawing_vision.analyze_drawing_entry

_ISOMETRIC_MARKER = "MODO DE AUDITORIA ISOMÉTRICA PROFUNDA"
_TILE_ORDER = ["top_left", "top_right", "bottom_left", "bottom_right"]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _entry_text(entry: dict[str, Any]) -> str:
    extracted = entry.get("extracted") or {}
    blocks: list[str] = []
    if extracted.get("kind") == "pdf":
        blocks.extend(str(page.get("text") or "") for page in (extracted.get("content") or [])[:3])
    return "\n".join(blocks)


def is_isometric_entry(entry: dict[str, Any]) -> bool:
    text = f"{entry.get('path', '')}\n{entry.get('filename', '')}\n{_entry_text(entry)}".casefold()
    indicators = (
        "isometric",
        "isometrics",
        "isométrico",
        "line identification",
        "bill of materials",
        "cont'd on",
        "piping support",
        "fwd :",
        "sb :",
        " el :",
        "-spl-",
    )
    score = sum(1 for indicator in indicators if indicator in text)
    return score >= 2 or entry.get("document_type") == "piping_isometric"


def _isometric_checklist() -> str:
    return """
MODO DE AUDITORIA ISOMÉTRICA PROFUNDA

Além das regras gerais, execute obrigatoriamente estas reconciliações:
A. CARIMBO E LINE DATA
- Transcreva drawing number, revisão, status, data, line number, diâmetro, spec/class, fluid code, design pressure/temperature, operating pressure/temperature, test pressure/type, NDT, insulation e coating.
- Compare esses campos entre carimbo, identificação da linha, notas, continuidades, BOM e documentos de referência. Não invente valores ilegíveis.

B. BOM/MTO E BALÕES
- Conte ocorrências dos balões por item e reconcilie com QTY da BOM, considerando que um conjunto flangeado pode repetir vários balões no mesmo ponto.
- Diferencie comprimento de tubo em metros de quantidade unitária.
- Para cada válvula, fitting, suporte e conjunto flangeado, informe se existe item correspondente na BOM.
- Compare material do componente com o escopo material da norma citada. Norma explicitamente restrita a aço não deve ser aceita automaticamente para corpo de bronze, Cu-Ni, ferro ou outro material; registre a contradição e solicite especificação alternativa.
- Referências retiradas/substituídas devem virar alerta de controle documental, salvo quando o projeto declarar edição congelada.

C. JUNTAS FLANGEADAS E PARAFUSOS
- Reconcilie stub end/flange, backing flange, gasket, stud bolts/nuts e, quando aplicável, washers.
- Calcule a quantidade implícita de prisioneiros por junta apenas quando o padrão estiver legível ou a BOM permitir a divisão exata.
- Não conclua falta de flange companheiro em uma continuidade para linha existente sem consultar a indicação de interface.

D. DIMENSÕES E SPOOLS
- Identifique spools e cadeias dimensionais por eixo.
- Some dimensões parciais somente quando compartilham as mesmas linhas de extensão e o mesmo trecho.
- Compare soma parcial com dimensão total. Informe os operandos e o resíduo.
- Antes de declarar erro, verifique se o resíduo corresponde a face-to-face de válvula, espessura de gasket, flange, fitting, gap de solda ou trecho não cotado. Sem confirmação, classifique como not_verifiable.
- Compare comprimentos de tubo da BOM com comprimentos retos cotados, tolerando arredondamento e descontando fittings/valves quando indicado.

E. CONTINUIDADES E INTERFACES
- Para cada CONT'D ON, extraia line number, size, EXIST/NEW, sheet, FWD, SB e EL.
- Detecte continuidade duplicada com coordenadas divergentes, mudança de size/spec sem reducer, ou interface NEW/EXIST sem método de conexão definido.

F. VÁLVULAS, FLUXO E SUPORTES
- Compare seta de fluxo com orientação de check valve. Sem P&ID ou símbolo legível, marque como não verificável.
- Reconcilie tags de válvula e suporte com BOM e desenhos/detalhes referenciados.
- Notas que deixam routing, supports, hydrotest vents/drains ou orientação para definição em campo devem ser registradas como hold point de fabricação, não automaticamente como erro de projeto.

G. EVIDÊNCIA
- Um achado bloqueante exige contradição explícita ou dois canais independentes: geometria, carimbo, BOM, balão, nota, continuidade, P&ID, line class ou desenho de suporte.
- Diga claramente quando algo está correto. Não gere achado apenas para preencher a resposta.

Acrescente ao JSON, além dos campos já pedidos:
"line_data":{},
"continuations":[{"line_number":"","size":"","state":"NEW|EXIST|UNKNOWN","sheet":"","fwd":null,"sb":null,"el":null,"evidence":""}],
"dimension_chains":[{"spool":"","axis":"","total":null,"partials":[],"sum_partials":null,"residual":null,"residual_explanation":"","status":"consistent|candidate_mismatch|not_verifiable","evidence":""}],
"flange_joint_sets":[{"location":"","size":"","flange_item":"","gasket_item":"","bolt_item":"","implied_bolt_quantity":null,"status":"complete|incomplete|not_verifiable","evidence":""}],
"support_checks":[{"support_tag":"","bom_item":"","referenced_detail":"","status":"matched|missing|not_verifiable","evidence":""}],
"valve_checks":[{"tag":"","bom_item":"","type":"","material":"","standard":"","flow_orientation":"","status":"consistent|candidate_mismatch|not_verifiable","evidence":""}],
"bom_reconciliation":[{"item":"","bom_quantity":null,"observed_quantity":null,"unit":"","status":"consistent|candidate_mismatch|not_verifiable","evidence":""}].
""".strip()


def overview_prompt(entry: dict[str, Any], page: dict[str, Any], knowledge: dict[str, Any]) -> str:
    base = _ORIGINAL_OVERVIEW_PROMPT(entry, page, knowledge)
    if not is_isometric_entry(entry):
        return base
    return f"{base}\n\n{_isometric_checklist()}\n\nEsta é uma prancha densa: solicite as quatro regiões ampliadas para conferir geometria, BOM, notas e carimbo."


def tile_prompt(
    entry: dict[str, Any],
    page: dict[str, Any],
    tile_name: str,
    overview: dict[str, Any],
    knowledge: dict[str, Any],
) -> str:
    base = _ORIGINAL_TILE_PROMPT(entry, page, tile_name, overview, knowledge)
    if not is_isometric_entry(entry):
        return base
    focus = {
        "top_left": "Priorize geometria, continuidades, reduções, tees, soldas, spools, coordenadas e cadeias dimensionais.",
        "top_right": "Priorize BOM/MTO, materiais, normas, quantidades, válvulas, flanges, gaskets e stud bolts; reconcilie com os balões.",
        "bottom_left": "Priorize spools, suportes, válvula, setas de fluxo, dimensões totais/parciais e notas gerais.",
        "bottom_right": "Priorize carimbo, revisão, status, line data, design/test data, NDT, referências e BOM inferior.",
    }.get(tile_name, "Revise todos os elementos isométricos legíveis.")
    return f"{base}\n\n{_ISOMETRIC_MARKER}\n{focus}\nRetorne também quaisquer line_data, continuations, dimension_chains, flange_joint_sets, support_checks, valve_checks e bom_reconciliation visíveis nesta região."


async def vision_request(image_path, prompt: str) -> dict[str, Any]:
    result = await _ORIGINAL_VISION_REQUEST(image_path, prompt)
    if _ISOMETRIC_MARKER in prompt and "REGIÃO AMPLIADA" not in prompt:
        result["needs_detail_tiles"] = list(_TILE_ORDER)
    return result


async def analyze_drawing_entry(entry: dict[str, Any]) -> dict[str, Any]:
    if not is_isometric_entry(entry):
        return await _ORIGINAL_ANALYZE(entry)
    previous_limit = drawing_vision.MAX_DETAIL_TILES
    drawing_vision.MAX_DETAIL_TILES = max(previous_limit, 4)
    try:
        result = await _ORIGINAL_ANALYZE(entry)
    finally:
        drawing_vision.MAX_DETAIL_TILES = previous_limit
    result["audit_mode"] = "piping_isometric_deep_review"
    result["isometric_checks_enabled"] = True
    return result


# Patch the functions used internally by drawing_vision and the references imported
# earlier by ai_batch_service.
drawing_vision._overview_prompt = overview_prompt
drawing_vision._tile_prompt = tile_prompt
drawing_vision._vision_request = vision_request
drawing_vision.analyze_drawing_entry = analyze_drawing_entry
ai_batch_service.analyze_drawing_entry = analyze_drawing_entry
