# Em core/injetor.py - SUBSTITUA O CONTEÚDO TODO

import json

from lxml import etree as ET  # 1. MUDANÇA IMPORTANTE: Usando a biblioteca lxml


def injetar_traducoes(arquivo_xml_original: str, mapa_traducoes, arquivo_xml_final: str):
    """
    Recebe um mapa (dicionário ou caminho de arquivo JSON) de XPath -> Tradução
    e aplica as mudanças no XML usando o poder do lxml.
    Retorna True em caso de sucesso, False em caso de falha.
    """
    try:
        # 2. LÓGICA MELHORADA: Se recebermos um caminho de arquivo, lemos o JSON.
        if isinstance(mapa_traducoes, str):
            with open(mapa_traducoes, encoding='utf-8') as f:
                mapa_xpath_traducao = json.load(f)
        else:
            mapa_xpath_traducao = mapa_traducoes

        # Usamos o parser do lxml, que é mais robusto
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.parse(arquivo_xml_original, parser)
        root = tree.getroot()
        
        itens_modificados = 0
        
        for xpath, traducao in mapa_xpath_traducao.items():
            # 3. MUDANÇA CRÍTICA: root.xpath() do lxml entende os endereços complexos
            elementos = root.xpath(xpath)
            if elementos:
                elementos[0].text = traducao
                itens_modificados += 1
        
        print(f"Injeção concluída. Itens modificados: {itens_modificados}")
        tree.write(arquivo_xml_final, encoding='utf-8', xml_declaration=True, pretty_print=True)
        return True
        
    except FileNotFoundError:
        print(f"ERRO no injetor: Arquivo não encontrado - {arquivo_xml_original} ou {mapa_traducoes}")
        return False
    except Exception as e:
        print(f"ERRO INESPERADO durante a injeção: {e}")
        return False