def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: lit les vrais fichiers data/raw/ (sans appel API Mistral/Qdrant)",
    )
