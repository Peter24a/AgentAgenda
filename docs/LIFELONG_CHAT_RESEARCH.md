# AgentAgenda: fuentes sobre memoria conversacional y contexto social

**Corte de investigación:** 14 de septiembre de 2026.

**Función de este documento:** referencia bibliográfica y fundamentos. La arquitectura, la migración PersonalLLM, la sincronización y el roadmap vigentes están consolidados en el [README](../README.md).

Los trabajos consultados permiten diseñar memoria persistente, pero no demuestran un asistente infalible durante toda una vida real. Las analogías cognitivas orientan funciones y experimentos; no reproducen conciencia ni constituyen una nueva técnica científica validada.

## 1. Contexto, memoria externa y aprendizaje

| Concepto | Qué cambia | Papel en AgentAgenda |
| --- | --- | --- |
| Contexto activo | Información que recibe el modelo en una llamada | Conversación reciente, pendientes y evidencia seleccionada. |
| Memoria externa | Registros persistentes que se consultan y actualizan | Primera opción para hechos personales, episodios, preferencias y acuerdos. |
| Aprendizaje del modelo | Pesos o módulos internos que se entrenan/adaptan | Línea futura de investigación, fuera del primer MVP. |

MemGPT formaliza gestión de memoria externa y contexto. Titans estudia módulos de memoria neuronal que aprenden durante la inferencia; Nested Learning/HOPE propone niveles de aprendizaje con distintas dinámicas. Estos últimos requieren cambios en el modelo y su ejecución: no son una opción que se active añadiendo un resumen a cualquier GGUF. [MemGPT](https://arxiv.org/abs/2310.08560), [Titans](https://arxiv.org/abs/2501.00663), [Nested Learning](https://arxiv.org/abs/2512.24695).

## 2. Técnicas existentes y avances recientes

Selección de fuentes primarias, con fechas de primera publicación cuando se indica un día. No es una revisión sistemática exhaustiva. Los resultados publicados por los autores orientan experimentos; no son garantías de rendimiento con el modelo local del proyecto.

### Bases que ya son relevantes

| Trabajo | Idea aprovechable | Límite y decisión para AgentAgenda |
| --- | --- | --- |
| [MemGPT — 12 oct 2023](https://arxiv.org/abs/2310.08560) | Administrar contexto activo y memoria externa mediante herramientas. | Tomar la separación de niveles; una ventana virtual no equivale a recuerdo ilimitado fiable. |
| [Zep/Graphiti — 20 ene 2025](https://arxiv.org/abs/2501.13956) | Episodios y relaciones con temporalidad. | Adoptar procedencia y vigencia; un grafo completo puede esperar a que consultas reales lo justifiquen. |
| [A-MEM — 17 feb 2025](https://arxiv.org/abs/2502.12110) | Notas atómicas enlazadas, inspiradas en Zettelkasten. | Encaja con la idea Obsidian del README. Cada enlace o reinterpretación generada necesita fuentes. |
| [HippoRAG 2 — 20 feb 2025](https://arxiv.org/abs/2502.14802) | Recuperación asociativa sobre pasajes y relaciones. | Su evaluación de conocimiento no demuestra vínculo conversacional de por vida. Considerarlo para preguntas que conecten varios episodios. |
| [Mem0 — 28 abr 2025](https://arxiv.org/abs/2504.19413) | Extracción incremental y decisiones de agregar, actualizar, eliminar o no cambiar. | Esas operaciones son útiles; la extracción con modelos alojados debe reevaluarse con llama.cpp. |

### Trabajos de 2025–2026 que revisaría primero

| Trabajo y fecha | Aportación | Aplicación y cautela |
| --- | --- | --- |
| [Hindsight — 14 dic 2025](https://arxiv.org/abs/2512.12818) | Distingue hechos, experiencias del agente, resúmenes de entidades y opiniones; retener, recuperar y reflexionar. | Candidato práctico para una comparación. El [repositorio oficial](https://github.com/vectorize-io/hindsight) documenta PostgreSQL/pgvector y proveedor `llamacpp`. Verificar toda la configuración local, incluidos embeddings y reranking; compatibilidad declarada no prueba calidad ni latencia en este equipo. |
| [EverMemOS — 5 ene 2026](https://arxiv.org/abs/2601.02163) | Ciclo de episodios, consolidación temática y recuperación; incluye señales sobre planes o estados con vigencia. | Muy próximo a la idea del README. Sus pruebas principales son de preguntas sobre memoria; varios comportamientos conversacionales/prospectivos se ilustran cualitativamente. Copiar principios no exige instalar toda su infraestructura. |
| [SimpleMem — 5 ene 2026](https://arxiv.org/abs/2601.02553) | Compresión estructurada, síntesis de información relacionada y recuperación según intención. | Útil para reducir coste. La expresión de los autores «semantic lossless compression» no demuestra conservación literal de todos los detalles; mantener fuentes para información exacta. |
| [LeanMem — 4 ago 2026](https://arxiv.org/abs/2608.03463v1) | Trata de forma distinta perfiles, eventos temporales y registros que requieren fidelidad; adapta el presupuesto de recuperación. | Especialmente pertinente: reporta pruebas con Qwen3-8B y GPT-4.1-mini. Preprint reciente; tomar su diferenciación por tipos como hipótesis a comprobar localmente. |
| [RuleMem — 3 sep 2026](https://arxiv.org/abs/2609.03915v1) | Induce reglas reutilizables para guiar recuperación y razonamiento. | Interesante para rutinas condicionadas. Una regularidad inferida no debe convertirse automáticamente en una preferencia ni en permiso para actuar. Trabajo muy reciente. |
| [LifeMem — 11 sep 2026](https://arxiv.org/abs/2609.12655) | Agrupa experiencias por procedimientos y extrae habilidades reutilizables entre tareas. | Referencia para una fase de aprendizaje de procedimientos; sus entornos de tareas no validan memoria autobiográfica ni comprensión social. |

**Elección propuesta:** comenzar con persistencia propia y un contrato sencillo de memoria. Comparar una implementación pequeña con Hindsight usando datos sintéticos en español. LeanMem y EverMemOS aportan criterios de organización; RuleMem y LifeMem quedarían para experimentos posteriores. No seleccionar una solución por un porcentaje aislado de LoCoMo: pueden variar modelo, preguntas, juez, presupuesto y configuración.

Un resultado particularmente relevante para modelos locales es [The Memory Trust Gap — 1 sep 2026](https://arxiv.org/abs/2609.01852). En pruebas controladas, memorias desactualizadas pueden imponerse a evidencia vigente; la mitigación depende de la capacidad del modelo. **Inferencia de ingeniería:** resolver vigencia y conflictos conocidos antes de ensamblar el prompt, en lugar de esperar que una instrucción verbal siempre los resuelva. Es un preprint y no una estimación de la frecuencia de fallos en AgentAgenda.

## 3. Qué tomar de neurociencia y de la dimensión social

Esta sección distingue funciones humanas, modelos explicativos y decisiones de ingeniería. Las capas de software no representan regiones cerebrales ni reproducen conciencia o experiencia subjetiva.

### 3.1. Tipos de memoria: una guía funcional

La neurociencia estudia mecanismos nerviosos; la psicología cognitiva modela capacidades; la sociología y la psicología social aportan contexto, relaciones y construcción de significado. Conviene combinar esas perspectivas sin atribuirles una única teoría completa del cerebro.

| Función humana | Explicación sencilla | Analogía útil para software |
| --- | --- | --- |
| Memoria de trabajo | Mantener y manipular lo necesario para una actividad en curso | Objetivo actual, restricciones, interlocutores y pregunta pendiente. |
| Memoria episódica | Recordar acontecimientos con su contexto | «El lunes hablaste con Juan sobre cambiar la entrega», con fecha y fuente. |
| Memoria semántica | Conocimiento y significados que no requieren revivir un episodio concreto | Preferencias y hechos generales, con evidencia y vigencia. |
| Memoria procedimental | Habilidades y maneras aprendidas de hacer algo | Procedimientos con condiciones y resultados registrados. |
| Memoria prospectiva | Recordar que hay que hacer algo después | Intenciones y compromisos activados por una fecha o condición. |

No son cinco cajones independientes. El modelo de [Baddeley (2000)](https://doi.org/10.1016/S1364-6613(00)01538-2) propone un buffer episódico que integra representaciones dentro de la memoria de trabajo. Los experimentos de [Cohen y Squire (1980)](https://pubmed.ncbi.nlm.nih.gov/7414331/) mostraron aprendizaje de una habilidad de lectura en personas con amnesia, apoyando la distinción entre saber hacer y recordar declarativamente. Esto inspira separar funciones, pero una receta textual de un agente no equivale a una habilidad motora humana.

La memoria prospectiva tampoco es simplemente una colección de recuerdos futuros: el marco de [McDaniel y Einstein (2000)](https://onlinelibrary.wiley.com/doi/10.1002/acp.775) distingue procesos de monitoreo y recuperación ante claves. **Decisión de diseño:** una intención con fecha debe tener activación operativa mediante el scheduler, además de poder consultarse en el chat.

### 3.2. Consolidación, reconstrucción y generalización

Consolidar puede implicar reorganización y transformación. [Ko et al. (Nature, 14 may 2025)](https://www.nature.com/articles/s41586-025-08993-1) observaron en **ratones** reorganización de circuitos hipocampales relacionada con pérdida de precisión y generalización. Es evidencia contra una analogía demasiado simple de «archivo exacto que se traslada a otro sitio»; no demuestra cómo implementar memoria en un LLM ni permite trasladar directamente esos resultados a personas.

En humanos, [Hupbach et al. (2007)](https://pmc.ncbi.nlm.nih.gov/articles/PMC1838545/) encontraron integración de información nueva en recuerdos episódicos bajo determinadas condiciones de reactivación. No significa que cada recuerdo se reescriba siempre que se consulta. **Decisión de diseño:** actualizar interpretaciones con versiones y conservar evidencia; una aplicación puede proteger la exactitud documental aunque tome inspiración de procesos humanos reconstructivos.

Un worker nocturno no reproduce el sueño. Aquí «consolidar» significa derivar episodios y generalizaciones trazables con un presupuesto de cómputo. El olvido humano tampoco justifica borrar al azar: relevancia, caducidad y eliminación son políticas de producto distintas.

### 3.3. La dimensión social cambia qué significa recordar

**Identidad y relato.** [Pasupathi (2001)](https://pubmed.ncbi.nlm.nih.gov/11548972/) propone que los relatos autobiográficos se construyen con interlocutores y contextos, y pueden influir en recuerdos posteriores e identidad. **Aplicación propuesta:** guardar «dijo que estaba cansado ese día», sin transformarlo en «es una persona poco constante». La persona puede cambiar y mantener preferencias diferentes según situación.

**Quién sabe qué.** La teoría de [memoria transactiva de Wegner (1987)](https://link.springer.com/chapter/10.1007/978-1-4612-4634-3_9) describe coordinación social sobre dónde reside el conocimiento. **Aplicación propuesta:** recordar qué documento, persona o herramienta es la fuente pertinente. Para una cita, consultar el calendario vigente; para su motivo, recuperar el episodio donde se explicó. No es necesario duplicar todo en un perfil universal.

**Contexto y circulación.** [Nissenbaum (2004)](https://nissenbaum.tech.cornell.edu/papers/H.%20Nissenbaum,%20_Privacy%20as%20Contextual%20Integrity.pdf) ofrece un marco normativo de privacidad que considera roles, contextos y flujos de información. **Aplicación propuesta:** una conversación personal y una consulta de un agente laboral pueden compartir almacenamiento y tener alcances de acceso distintos. Las etiquetas de tema ayudan a buscar; los permisos determinan qué se puede usar.

**Acuerdo compartido.** Para AgentAgenda propongo distinguir `mencionado`, `propuesto`, `aceptado`, `realizado` y `cancelado`. Que el asistente repita una idea no demuestra acuerdo mutuo; el silencio tampoco confirma una propuesta. El estado compartido debe representar evidencia de aceptación y el resultado real de las acciones.

Ejemplo inventado: «Antes prefería reuniones presenciales; ahora remotas, excepto con el equipo de laboratorio». Esto requiere una preferencia con historia y una excepción contextual. Un perfil plano con `modalidad=remota` perdería parte de lo que la persona quiso decir.

### 3.4. Evitar que el asistente invente la autobiografía del usuario

[Pataranutaporn et al., IUI 2025, *Slip Through the Chat*](https://doi.org/10.1145/3708359.3712112) estudiaron 180 participantes y observaron formación de recuerdos falsos en condiciones con información deliberadamente engañosa y conversación con un chatbot. Ese experimento no establece que cualquier chat cotidiano tenga ese efecto. Sí justifica evaluar cuidadosamente cómo el asistente reconstruye episodios personales.

**Decisión de diseño:** mostrar la procedencia cuando se recuerda algo, distinguir palabras originales de resúmenes e inferencias, y decir «no encuentro ese detalle» cuando falta. Una respuesta narrativa convincente no debe convertirse en una nueva fuente que después confirme su propia invención.

## 4. Evaluaciones de referencia

[LongMemEval](https://arxiv.org/abs/2410.10813) evalúa extracción, razonamiento entre sesiones, temporalidad, actualización y abstención. [LoCoMo](https://aclanthology.org/2024.acl-long.747/) aporta conversaciones extensas semisintéticas verificadas/editadas por humanos. Son pruebas útiles y limitadas, no demostraciones de convivencia durante décadas.

[BEAM/LIGHT](https://arxiv.org/abs/2510.27246) estudia historias mucho mayores y combina memoria episódica, de trabajo y un registro de hechos relevantes. Sus resultados muestran dificultades en esas pruebas incluso con ventanas muy extensas.

[MemOps — 14 jul 2026](https://arxiv.org/abs/2607.12893) evalúa operaciones de recordar, actualizar, olvidar y seguir cambios con evidencia, además de respuestas finales. [LongMemEval-V2 — 12 may 2026](https://arxiv.org/abs/2605.12493) se orienta a experiencia y procedimientos de agentes. Los criterios de aceptación específicos de AgentAgenda están en el README.

## 5. Alcance de la evidencia

Se consultaron fuentes primarias y documentación oficial. No se instalaron los sistemas de memoria ni se ejecutaron sus benchmarks con el modelo local. Comparaciones de los autores pueden variar en preguntas, jueces, modelos y presupuesto; no constituyen un ranking universal. Las propuestas de aplicación son inferencias de ingeniería que deben medirse en este proyecto.
