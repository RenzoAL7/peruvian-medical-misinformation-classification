# Auditoría de fuentes de descubrimiento

Esta tabla documenta decisiones técnicas de descubrimiento. No asigna
veracidad a ninguna fuente ni reemplaza la revisión humana.

## Fuentes activas

| Fuente | Rol | Método | Límite por corrida |
| --- | --- | --- | ---: |
| El Comercio | medio periodístico | archivo de salud | 2 |
| La República | medio periodístico | archivo de salud | 2 |
| Diario Correo | medio periodístico | archivo de salud | 2 |
| Diario Ojo | medio periodístico | archivo de salud | 2 |
| MINSA | fuente institucional | notas de prensa | 2 |
| Gestión | medio periodístico | etiqueta de salud, limitada a artículos de Perú | 2 |
| El Popular | medio periodístico | sección Vida más filtro médico | 2 |
| Canal N | medio periodístico | etiqueta de salud | 2 |

La meta global sigue siendo 12. Tener ocho fuentes permite reemplazar la cuota
faltante de una página sin forzar resultados irrelevantes ni gastar créditos de
NewsData. La selección usa rondas entre fuentes y rota el orden entre corridas.

## Fuentes probadas y no activas

| Fuente | Resultado observado | Decisión actual |
| --- | --- | --- |
| Latina Noticias | la página devolvió principalmente política, administración o piezas de video | no activa para el corpus textual |
| RPP Vital | las muestras probadas entregaron cuerpos de aproximadamente 58 palabras | no activa mientras no supere el mínimo textual |
| Perú21 | `robots.txt` no permite el archivo probado | no automatizar |
| El Peruano | la consulta válida de NewsData devolvió cero resultados | no gastar nuevos créditos sin evidencia de cobertura |
| TVPerú | el servidor respondió 403 al agente académico probado | no automatizar |
| Expreso | `robots.txt` rechazó la ruta de salud probada y el servidor respondió 403 | no automatizar |
| Agencia Andina | la sección de salud respondió HTTP 500 en la prueba | reintentar en una auditoría futura |

Una fuente puede reincorporarse si una prueba nueva confirma acceso permitido,
URLs de artículos, texto suficiente y rendimiento temático. Los resultados de
una sola corrida no se presentan como una evaluación permanente del medio.
