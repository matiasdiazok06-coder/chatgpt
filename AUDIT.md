# Auditoría del repositorio

## Resumen ejecutivo
- Aplicación CLI para gestionar cuentas de Instagram, leads y envíos de mensajes masivos.
- Las funciones principales dependen de sesiones guardadas de `instagrapi` y de la API de OpenAI para el auto-responder.
- Se detectaron problemas críticos con compatibilidad de dependencias, ineficiencias y código duplicado.

## Problemas detectados

### P1 · Críticos
1. **Compatibilidad con `openai` 0.x rompe el auto-responder**
   El código usa la clase moderna `OpenAI` de la versión >=1.0 del SDK, pero `requirements.txt` no fija la versión mínima. Si se
 instala la rama 0.x (aún muy difundida), la importación falla y el bot responde siempre con el mensaje de fallback, dejando inu
tilizable la función. 【F:responder.py†L20-L35】【F:requirements.txt†L1-L4】
   _Sugerencia:_ fijar `openai>=1.0.0` en `requirements.txt` o adaptar el código a la API antigua (`openai.ChatCompletion.create`).

### P2 · Moderados
1. **Opciones de concurrencia sin efecto en el envío de DMs**
   `menu_send_rotating` pide la cantidad de cuentas simultáneas pero nunca usa la variable `concurr`, por lo que el envío sigue
siendo totalmente secuencial. Esto puede confundir a los usuarios y limita el throughput prometido. 【F:ig.py†L46-L117】
   _Sugerencia:_ implementar un pool de workers/hilos o eliminar el prompt hasta que exista la característica.
2. **Cuentas sin sesión bloquean el auto-responder en cada iteración**
   Se valida una vez que exista el archivo `.sessions`, pero si falla se deja al usuario en la lista de `targets`. El bucle infinito vuelve a intentarlo en cada iteración generando advertencias permanentes y sin progreso. 【F:responder.py†L52-L94】
   _Sugerencia:_ filtrar `targets` tras la validación inicial o pausar/reintentar con backoff.
3. **Búsqueda de leads ya contactados escala lineal por envío**
   `already_contacted` lee y parsea todo el log JSONL cada vez que se procesa un lead, con lo que el costo crece cuadráticamente en campañas largas. 【F:storage.py†L14-L27】
   _Sugerencia:_ precargar el archivo en un `set` o cachearlo en memoria antes del bucle principal.

### P3 · Leves
1. **Duplicación de lógica de clientes de Instagram**
   `_client_for` aparece idéntico en `ig.py` y `responder.py`, y además existe un backup completo `ig.py.bak_concurr_order2`. Esto incrementa el mantenimiento y riesgo de divergencia. 【F:ig.py†L22-L34】【F:responder.py†L9-L18】【F:ig.py.bak_concurr_order2†L1-L117】
   _Sugerencia:_ mover la función común a un módulo compartido (`instagram_client.py`) y eliminar backups del repo.
2. **Importaciones sin uso y dependencias implícitas**
   Varios archivos importan módulos que nunca utilizan (`json`, `os`, `sys`, `random`, etc.), lo cual dificulta auditar dependencias reales. También `storage.py` importa `ask` aunque no lo usa. 【F:ig.py†L3-L9】【F:responder.py†L3-L7】【F:storage.py†L3-L6】

   _Sugerencia:_ limpiar imports y dejar explícitas sólo las dependencias necesarias.
3. **Menú Supabase sólo muestra un texto**
   La opción 6 del menú principal no implementa integración real; sólo imprime instrucciones, lo que puede percibirse como característica rota. 【F:app.py†L36-L50】【F:storage.py†L52-L56】
   _Sugerencia:_ documentar que es un placeholder o implementar la funcionalidad real.

## Funciones o scripts propensos a fallar
- `accounts.menu_accounts` > opción 4 llama a `_login_and_save_session`; cualquier challenge/2FA de Instagram hace que la conexión falle y la cuenta quede marcada como no conectada. 【F:accounts.py†L101-L118】
- `_client_for` (tanto en `ig.py` como en `responder.py`) lanza un `RuntimeError` si falta el archivo `.sessions/<username>.json`, lo que provoca que los envíos fallen silenciosamente. 【F:ig.py†L22-L34】【F:responder.py†L9-L18】
- `menu_autoresponder` depende de una `OPENAI_API_KEY` válida y de tener hilos sin respuestas propias; de lo contrario, ignora mensajes o responde siempre con el fallback. 【F:responder.py†L37-L94】

## Variables de entorno / `.env`
- `INSTACLI_EMOJI`: desactiva emojis en terminales que no los soportan. 【F:utils.py†L22-L35】
- Parámetros de rate limit y delays: se cargan desde `.env` o `.env.local`, con prioridad para variables del entorno. 【F:config.py†L1-L59】
- `OPENAI_API_KEY`: solicitada al iniciar el auto-responder y puede reutilizarse desde el entorno presionando Enter. 【F:responder.py†L50-L89】
- `SUPABASE_URL` y `SUPABASE_KEY`: mencionadas para una integración opcional. 【F:storage.py†L52-L56】

## Ejecución local en macOS
1. Instalar dependencias y crear el entorno virtual ejecutando `./setup_mac.sh`, que selecciona Python 3.11/3.10, crea `venv311` e instala `requirements.txt`. 【F:setup_mac.sh†L1-L20】
2. Activar el entorno y lanzar el menú con `./run_mac.sh` (carga el virtualenv y ejecuta `python3 app.py`). 【F:run_mac.sh†L1-L13】
3. Alternativamente, seguir las instrucciones del README específico para macOS. 【F:README_MAC.md†L1-L31】
4. Librerías mínimas: `instagrapi`, `openai` (ver nota sobre versión), `colorama`, `pyinstaller`, más las transitivas que instala `setup_mac.sh` (p. ej. `pydantic`, `Pillow`, `requests`, `rich`). 【F:requirements.txt†L1-L4】【F:setup_mac.sh†L7-L18】

## Próximos pasos sugeridos
- Fijar versiones compatibles en `requirements.txt` y agregar un `pip check`/tests básicos.
- Centralizar acceso a sesiones de Instagram y limpiar duplicados/backups del repositorio.
- Añadir caching en `storage.already_contacted` y pruebas automatizadas que cubran los flujos de envío y auto-respuesta.

