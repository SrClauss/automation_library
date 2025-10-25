from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Iterable, Callable

# Tipo para representar uma sessão (ex: driver do Selenium, sessão de requests)
Session = Any

# Tipo para representar um item de dados extraído
DataItem = Dict[str, Any]

# Tipo para um item da fila de tarefas
TaskItem = Any


class BaseAuthenticator(ABC):
    """Interface para classes de autenticação.

    O método `login` aceita um parâmetro opcional `ready_callback` que, quando
    informado, deverá ser chamado pelo implementador assim que o driver
    estiver totalmente pronto (por exemplo: após navegar para a página
    inicial, lidar com popups, etc.). Isso permite que a UI mostre com precisão
    quando um worker passou do estado "logging_in" para "ready".
    """

    @abstractmethod
    def login(self, ready_callback: Optional[Callable] = None) -> Session:
        """Executa o processo de login e retorna um objeto de sessão.

        Se `ready_callback` for fornecido, ele deve ser invocado quando o
        driver estiver pronto; o callback pode aceitar o driver como
        argumento ou nenhum parâmetro.
        """
        raise NotImplementedError()

    @abstractmethod
    def logout(self, session: Session):
        """Encerra a sessão e realiza qualquer limpeza necessária."""
        raise NotImplementedError()


class BaseExtractor(ABC):
    """Interface para classes de extração de dados.

    Recebe uma sessão e um item da tarefa, e retorna os dados extraídos.
    """

    @abstractmethod
    def extract(self, session: Session, task_item: TaskItem) -> DataItem:
        """Usa a sessão para extrair dados com base no item da tarefa.

        Retorna um dicionário com os dados.
        """
        raise NotImplementedError()


class BaseStorage(ABC):
    """Interface para classes de persistência de dados.

    Abstrai onde e como os dados são salvos (Excel, DB, etc.).
    """

    @abstractmethod
    def open(self):
        """Prepara o armazenamento para escrita (ex: abre conexão, carrega arquivo)."""
        raise NotImplementedError()

    @abstractmethod
    def save_items(self, items: List[DataItem]):
        """Salva uma lista de itens de dados no armazenamento."""
        raise NotImplementedError()

    @abstractmethod
    def close(self):
        """Finaliza a operação de escrita (ex: fecha conexão, salva arquivo)."""
        raise NotImplementedError()

    @abstractmethod
    def get_processed_items(self) -> Iterable[TaskItem]:
        """Retorna um iterável de itens que já foram processados e salvos.

        Usado para permitir continuação de um trabalho interrompido.
        """
        raise NotImplementedError()

