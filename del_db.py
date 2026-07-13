import os, time
path = r'C:\Users\ATouray\relay-local\app\instance\relay.db'
try:
    os.remove(path)
    print("Deleted")
except PermissionError:
    print("Locked - trying to force...")
    os.system('taskkill /F /IM python.exe 2>nul')
    time.sleep(2)
    try:
        os.remove(path)
        print("Deleted after kill")
    except Exception as e:
        print(f"Still locked: {e}")
        # Try alternate path
        path2 = r'C:\Users\ATouray\relay-local\instance\relay.db'
        try:
            os.remove(path2)
            print(f"Deleted {path2}")
        except:
            print(f"Can't delete either")
