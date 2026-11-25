import hashlib
import json
from pathlib import Path

def generate_manifest():
    scripts_dir = Path("core/scripts")
    manifest = {}
    
    print(f"Gerando manifesto para scripts em {scripts_dir}...")
    
    for ps1 in scripts_dir.rglob("*.ps1"):
        # Gera o hash do arquivo
        hash_sha256 = hashlib.sha256(ps1.read_bytes()).hexdigest()
        # Usa o caminho relativo como chave (ex: dashboard/repair_agent.ps1)
        rel_path = ps1.relative_to(scripts_dir).as_posix()
        manifest[rel_path] = hash_sha256
        print(f"  [OK] {rel_path} -> {hash_sha256[:8]}...")
        
    manifest_path = scripts_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
    print(f"\nManifesto salvo em: {manifest_path}")
    print(f"Total de scripts protegidos: {len(manifest)}")

if __name__ == "__main__":
    generate_manifest()