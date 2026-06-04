import json
import os


class I18nManager:
    def __init__(self, language="pt_BR"):
        self.translations = {}
        self.language = language
        self.locales_path = os.path.join(os.path.dirname(__file__), '..', 'locales')
        self.load_language(self.language)

    def load_language(self, language):
        filepath = os.path.join(self.locales_path, f"{language}.json")
        try:
            with open(filepath, encoding='utf-8') as f:
                self.translations = json.load(f)
                self.language = language
        except FileNotFoundError:
            print(f"Arquivo de idioma '{language}.json' não encontrado. Usando 'en_US' como padrão.")
            # Se o idioma escolhido falhar, tenta carregar o inglês como fallback
            if language != "en_US":
                self.load_language("en_US")

    def get(self, key, **kwargs):
        """
        Retorna o texto traduzido para a chave fornecida.
        Permite formatação de strings, ex: get("chave", nome="Mundo")
        """
        text = self.translations.get(key, key) # Retorna a própria chave se não encontrar
        if kwargs:
            return text.format(**kwargs)
        return text