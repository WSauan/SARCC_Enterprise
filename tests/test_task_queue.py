import pytest
import queue
from unittest.mock import MagicMock
from core.task_queue import TaskWorker, WorkerSignals

def test_task_worker_base64_injection(mocker):
    """Garante que a fila de tarefas substitui a tag {{script_b64}} corretamente."""
    
    # Simula a conexão remota para não tentar ligar de verdade
    mock_conn_class = mocker.patch("core.task_queue.RemoteConnectionManager")
    mock_conn_instance = mock_conn_class.return_value
    mock_conn_instance.execute_script.return_value = {
        "status": "Sucesso", 
        "json_data": {"StatusFinal": "SUCESSO"}, 
        "log_saida": ""
    }

    # Simula o banco de dados
    mock_db = MagicMock()
    
    # Prepara uma fila falsa com 1 tarefa de teste
    test_queue = queue.Queue()
    signals = WorkerSignals()
    
    # Argumentos: target_pc, script_name, script_content, module_name, credentials, script_b64, signals
    tarefa_falsa = (
        "PC-TESTE", 
        "Teste Agendador", 
        "Execute-Isso -Payload '{{script_b64}}'", 
        "Modulo Teste", 
        None, 
        "QmFzZTY0VGVzdGU=", # "Base64Teste" codificado
        signals
    )
    test_queue.put(tarefa_falsa)
    test_queue.put(None) # Sinal para o worker parar
    
    # Executa o worker
    worker = TaskWorker(test_queue, mock_db)
    worker.run()
    
    # Verifica se a injeção do script_b64 ocorreu antes de ser enviado ao RemoteConnectionManager
    mock_conn_instance.execute_script.assert_called_once_with(
        "PC-TESTE", 
        "Execute-Isso -Payload 'QmFzZTY0VGVzdGU='"
    )