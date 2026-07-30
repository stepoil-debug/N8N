# Método de auditoria profunda de isométricos

O módulo de isométricos cruza evidência visual e textual sem versionar desenhos de clientes.

## Verificações obrigatórias

- carimbo, revisão, line number, spec, fluid, design/operating/test data e NDT;
- BOM/MTO versus balões e geometria;
- materiais versus escopo da norma citada;
- conjuntos flangeados: stub end/flange, backing flange, gasket e stud bolts/nuts;
- comprimentos de tubo e cadeias dimensionais, com resíduos explicitados;
- continuidades NEW/EXIST, sheet, FWD, SB e EL;
- setas de fluxo versus orientação de check valve;
- suportes versus BOM e detalhes referenciados;
- notas que criam hold points de levantamento de campo, fabricação ou hidroteste.

## Política de evidência

Uma suspeita não vira erro confirmado somente porque o modelo reconheceu um símbolo. Achados bloqueantes exigem contradição explícita ou dois canais independentes, como BOM + balão, geometria + dimensão, carimbo + continuidade ou material + escopo da norma.

Documentos reais usados para validação permanecem fora do GitHub. Os testes automatizados utilizam somente entradas sintéticas.
