
import json
import os
import sys

# Permite executar este script tanto a partir da raiz do projeto quanto a partir do diretório
# `automation_library` (útil durante desenvolvimento). Se o pacote `automation_library`
# não estiver importável, adicionamos o diretório pai ao sys.path.
if __name__ == "__main__" and __package__ is None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

from core.ui import FrameworkGUI
from adapters.automation_adapter import AtlasCopcoAuthenticator, AtlasCopcoExtractor
from adapters.storage.excel_storage import ExcelStorage

def main():
    """
    Ponto de entrada para a aplicação com interface gráfica.
    
    Este script monta a aplicação, injetando as implementações específicas
    (autenticação, extração, armazenamento) na GUI genérica do framework.
    """
    # 1. Carrega a configuração geral
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Erro: config.json não encontrado!")
        return
    except json.JSONDecodeError:
        print("Erro: Falha ao decodificar config.json!")
        return

    # 2. Inicia a aplicação GUI, injetando as classes de implementação
    app = FrameworkGUI(
        authenticator_class=AtlasCopcoAuthenticator,
        extractor_class=AtlasCopcoExtractor,
        storage_class=ExcelStorage,
        config=config
    )

    # 3. Define o comportamento ao fechar a janela e inicia o loop principal
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

if __name__ == "__main__":
    main()
