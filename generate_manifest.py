import hashlib
import json
import os


def generate_manifest():
    scripts_dir = "core/scripts"
    manifest = {}

    print(f"Gerando manifesto para scripts em {scripts_dir}...")

    # Varre o diretório recursivamente
    for root, dirs, files in os.walk(scripts_dir):
        # Ignora pastas de backup
        if "backup" in root.lower() or "Scripts " in root:
            continue

        for file in files:
            if file.endswith(".ps1"):
                # Caminho completo e relativo
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, scripts_dir).replace("\\", "/")

                # Gera o hash
                with open(file_path, "rb") as f:
                    hash_sha256 = hashlib.sha256(f.read()).hexdigest()

                manifest[rel_path] = hash_sha256
                print(f"  [OK] {rel_path} -> {hash_sha256[:8]}...")

    manifest_path = os.path.join(scripts_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)

    print(f"\nManifesto salvo em: {manifest_path}")
    print(f"Total de scripts protegidos: {len(manifest)}")

if __name__ == "__main__":
    generate_manifest()
