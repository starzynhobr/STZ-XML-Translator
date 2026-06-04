import json
import logging
import os
import time

from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from core.extrator import extrair_textos
from core.injetor import injetar_traducoes
from core.tradutor_api import traduzir_arquivo_json

# --- CONFIGURAÇÃO INICIAL ---

load_dotenv(dotenv_path="./.env")
API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Tags configuráveis via env vars com fallback para valores genéricos
PARENT_TAG = os.getenv("PIPELINE_PARENT_TAG", "")
TARGET_TAG = os.getenv("PIPELINE_TARGET_TAG", "dispName")

base_path = os.getenv("PIPELINE_BASE_PATH", ".")
paths = {
    "originais": os.path.join(base_path, "01_ORIGINAIS"),
    "para_traduzir": os.path.join(base_path, "02_PARA_TRADUZIR_JSON"),
    "em_revisao": os.path.join(base_path, "03_EM_REVISAO_JSON"),
    "aprovados": os.path.join(base_path, "04_APROVADOS_JSON"),
    "traduzidos": os.path.join(base_path, "05_TRADUZIDOS_XML"),
    "logs": os.path.join(base_path, "LOGS"),
}

os.makedirs(paths["logs"], exist_ok=True)
log_file = os.path.join(paths["logs"], "pipeline.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)


class AutomationHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        filename = os.path.basename(file_path)
        file_dir = os.path.dirname(os.path.abspath(file_path))

        # ETAPA 1: Novo XML na pasta de ORIGINAIS
        if file_dir == os.path.abspath(paths["originais"]) and filename.endswith(".xml"):
            logging.info(f"Detectado novo XML: {filename}. Iniciando extração.")
            json_saida = os.path.join(paths["para_traduzir"], filename.replace(".xml", ".json"))
            sucesso, dados = extrair_textos(file_path, PARENT_TAG, TARGET_TAG)
            if sucesso:
                with open(json_saida, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                logging.info("Extração concluída. JSON gerado em 02_PARA_TRADUZIR_JSON.")
            else:
                logging.error(f"Falha na extração de {filename}: {dados}")

        # ETAPA 2: Novo JSON na pasta PARA_TRADUZIR
        elif file_dir == os.path.abspath(paths["para_traduzir"]) and filename.endswith(".json"):
            logging.info(f"Detectado JSON para tradução: {filename}. Acionando API Gemini.")
            json_revisao = os.path.join(paths["em_revisao"], filename)
            if traduzir_arquivo_json(file_path, json_revisao, API_KEY):
                logging.info("Tradução da API concluída. Arquivo movido para 03_EM_REVISAO_JSON.")
                os.remove(file_path)
            else:
                logging.error(f"Falha na tradução via API de {filename}.")

        # ETAPA 3: JSON movido para APROVADOS
        elif file_dir == os.path.abspath(paths["aprovados"]) and filename.endswith(".json"):
            logging.info(f"Detectado JSON aprovado: {filename}. Injetando tradução no XML.")
            xml_original = os.path.join(paths["originais"], filename.replace(".json", ".xml"))
            xml_final = os.path.join(paths["traduzidos"], filename.replace(".json", "_TRADUZIDO.xml"))

            if os.path.exists(xml_original):
                if injetar_traducoes(xml_original, file_path, xml_final):
                    logging.info(f"PROCESSO CONCLUÍDO para {filename}! XML final salvo em 05_TRADUZIDOS_XML.")
                else:
                    logging.error(f"Falha ao injetar traduções para {filename}.")
            else:
                logging.warning(f"XML original para {filename} não encontrado na pasta 01_ORIGINAIS.")


if __name__ == "__main__":
    logging.info("Iniciando o Vigia da Automação...")

    for path in paths.values():
        os.makedirs(path, exist_ok=True)

    event_handler = AutomationHandler()
    observer = Observer()

    observer.schedule(event_handler, paths["originais"], recursive=False)
    observer.schedule(event_handler, paths["para_traduzir"], recursive=False)
    observer.schedule(event_handler, paths["aprovados"], recursive=False)

    observer.start()
    logging.info("Vigia iniciado. Monitorando pastas...")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    logging.info("Vigia encerrado.")
