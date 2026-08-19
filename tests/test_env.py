import sys
from pathlib import Path

# Lisätään projektin juuri Pythonin moduulipolkuun
# Koska skripti on nyt tests/ -kansiossa, projektin juuri on yhden tason ylempänä
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.tools.code_runner import execute_python_code
from app.tools.file_tools import write_file, read_file, list_files
from app.memory.conversation import init_db

print("🔍 Tarkistetaan Local AI Platform -ympäristöä...\n")

# 1. Tarkistetaan tietokanta
try:
    init_db()
    print("✅ SQLite-tietokannan alustus: OK")
except Exception as e:
    print(f"❌ SQLite-virhe: {e}")

# 2. Testataan tiedostotyökalut
try:
    write_res = write_file("diag_test.txt", "Local AI Test Content")
    read_res = read_file("diag_test.txt")
    files_res = list_files()
    if read_res.get("content") == "Local AI Test Content":
        print("✅ Tiedostojen luku ja kirjoitus (workspace): OK")
    else:
        print("❌ Tiedostotyökalu palautti väärää dataa.")
except Exception as e:
    print(f"❌ Tiedostotyökaluvirhe: {e}")

# 3. Testataan koodinajohiekkalaatikko
try:
    code_res = execute_python_code("print(sum([10, 20, 30]))")
    if code_res.get("stdout") == "60":
        print("✅ Python-hiekkalaatikko ja koodin suoritus: OK")
    else:
        print(f"❌ Koodinajo epäonnistui: {code_res}")
except Exception as e:
    print(f"❌ Koodinajovirhe: {e}")

print("\n🚀 Kaikki valmiina! Voit nyt ajaa: .\\start.bat")