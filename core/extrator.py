# Em core/extrator.py - SUBSTITUA O CONTEÚDO TODO

import os
import xml.etree.ElementTree as ET


def get_xpath(elem, root, parent_map):
    """Gera um XPath único para um elemento, compatível com a biblioteca padrão."""
    path_parts = []
    while elem in parent_map:
        parent = parent_map[elem]
        siblings = list(parent)
        
        siblings_with_same_tag = [sib for sib in siblings if sib.tag == elem.tag]
        
        # Encontra o índice do elemento entre seus irmãos de mesma tag
        index = siblings_with_same_tag.index(elem) + 1
        
        path_parts.insert(0, f"{elem.tag}[{index}]")
        elem = parent

    # Adiciona a tag raiz no início do caminho
    path_parts.insert(0, root.tag)
    return '/' + '/'.join(path_parts)


def extrair_textos(arquivo_xml, parent_tag, target_tag):
    """
    Lê um XML e extrai o XPath/texto das tags alvo.
    Se parent_tag for vazio, busca em todo o arquivo.
    Retorna uma tupla: (sucesso, dados)
    """
    try:
        tree = ET.parse(arquivo_xml)
        root = tree.getroot()
        
        # --- LÓGICA DE BUSCA APRIMORADA ---
        # Se o usuário não digitar uma Tag Pai, procuramos a Tag Alvo em todo o documento.
        if parent_tag:
            xpath_query = f'.//{parent_tag}/{target_tag}'
        else:
            xpath_query = f'.//{target_tag}' # Busca geral

        elementos_alvo = root.findall(xpath_query)

        if not elementos_alvo:
            msg = f"AVISO: Nenhuma tag <{target_tag}> foi encontrada."
            if parent_tag:
                msg += f" dentro de <{parent_tag}>"
            print(msg)
            return (False, msg)

        # --- CORREÇÃO DO BUG DE XPATH ---
        # Cria um mapa de pais para que a função get_xpath funcione corretamente
        parent_map = {c: p for p in root.iter() for c in p}
        mapa_xpath_texto = {}

        for elem in elementos_alvo:
            if elem.text and elem.text.strip():
                # Passa o parent_map para a função corrigida
                xpath = get_xpath(elem, root, parent_map)
                mapa_xpath_texto[xpath] = elem.text.strip()
        
        # Garante que não retornamos um dicionário vazio se nenhum texto for encontrado
        if not mapa_xpath_texto:
            return (False, f"AVISO: Tags <{target_tag}> foram encontradas, mas não continham texto.")

        return (True, mapa_xpath_texto)
        
    except ET.ParseError as e:
        msg = f"ERRO CRÍTICO: O arquivo '{os.path.basename(arquivo_xml)}' não é um XML válido.\n\nDetalhes: {e}"
        print(msg)
        return (False, msg)
    except Exception as e:
        msg = f"ERRO INESPERADO durante a extração: {e}"
        print(msg)
        return (False, msg)