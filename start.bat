@echo off
cd /d "%~dp0"
echo Запускаю магазин Mebel Almaty...
echo.
echo 1) Python API:  http://127.0.0.1:8780/
echo 2) Для разработки React: npm install ^&^& npm run dev  (http://127.0.0.1:5173/)
echo 3) Для продакшена: npm run build — сервер отдаст dist/
echo.
echo Сайт откроется на http://127.0.0.1:8780/
start "" http://127.0.0.1:8780/
python server.py
pause
