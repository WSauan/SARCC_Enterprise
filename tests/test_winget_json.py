import json

def test_winget_json_parsing_structure():
    """Valida a estrutura de JSON que o novo script PS vai processar."""
    raw_json = """
    {
        "Sources": [
            {
                "Packages": [
                    {
                        "PackageIdentifier": "VideoLAN.VLC",
                        "PackageName": "VLC media player",
                        "InstalledVersion": "3.0.18",
                        "AvailableVersion": "3.0.20",
                        "Source": "winget"
                    },
                    {
                        "PackageIdentifier": "Mozilla.Firefox",
                        "PackageName": "Mozilla Firefox",
                        "InstalledVersion": "115.0",
                        "AvailableVersion": "115.0",
                        "Source": "winget"
                    }
                ]
            }
        ]
    }
    """
    data = json.loads(raw_json)
    packages = data["Sources"][0]["Packages"]
    
    assert len(packages) == 2
    assert packages[0]["PackageIdentifier"] == "VideoLAN.VLC"
    assert packages[0]["AvailableVersion"] == "3.0.20"