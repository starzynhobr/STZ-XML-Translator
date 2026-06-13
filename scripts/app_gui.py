import json
import os
import sys
import threading
import time
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

# Importa as funções dos nossos outros scripts
from extrator import extrair_textos
from i18n import I18nManager
from injetor import injetar_traducoes
from tradutor_api import traduzir_texto_unico


def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        # PyInstaller cria uma pasta temp e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Define a aparência padrão do aplicativo
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- NOVO: Janela de Gerenciamento do Glossário ---
class GlossaryWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.transient(master)
        self.i18n = self.master.i18n
        self.title(self.i18n.get("glossary_window_title"))
        self.geometry("600x400")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.glossary_path = resource_path(os.path.join("scripts", "glossario.json"))
        self.glossary_data = self.load_glossary()
        self.entries = []

        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text=self.i18n.get("glossary_terms_label"))
        self.scrollable_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.rebuild_ui()

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill="x", padx=10, pady=10)

        self.add_button = ctk.CTkButton(button_frame, text=self.i18n.get("glossary_add_button"), command=self.add_row)
        self.add_button.pack(side="left", padx=5)

        self.save_button = ctk.CTkButton(button_frame, text=self.i18n.get("glossary_save_button"), command=self.save_and_close)
        self.save_button.pack(side="right", padx=5)

    def load_glossary(self):
        if os.path.exists(self.glossary_path):
            with open(self.glossary_path, encoding='utf-8') as f:
                return json.load(f)
        return {}

    def rebuild_ui(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.entries = []
        for i, (key, value) in enumerate(self.glossary_data.items()):
            self.create_row(i, key, value)

    def create_row(self, index, key, value):
        key_entry = ctk.CTkEntry(self.scrollable_frame)
        key_entry.insert(0, key)
        key_entry.grid(row=index, column=0, padx=5, pady=5, sticky="ew")

        value_entry = ctk.CTkEntry(self.scrollable_frame)
        value_entry.insert(0, value)
        value_entry.grid(row=index, column=1, padx=5, pady=5, sticky="ew")

        delete_button = ctk.CTkButton(self.scrollable_frame, text="X", width=20, fg_color="red", hover_color="darkred", command=lambda i=index: self.delete_row(i))
        delete_button.grid(row=index, column=2, padx=5, pady=5)

        self.entries.append((key_entry, value_entry))
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        self.scrollable_frame.grid_columnconfigure(1, weight=1)

    def add_row(self):
        self.create_row(len(self.entries), "", "")

    def delete_row(self, index):
        self.glossary_data.pop(list(self.glossary_data.keys())[index])
        self.rebuild_ui()

    def save_and_close(self):
        new_glossary = {}
        for key_entry, value_entry in self.entries:
            key = key_entry.get().strip()
            value = value_entry.get().strip()
            if key and value:
                new_glossary[key] = value

        with open(self.glossary_path, 'w', encoding='utf-8') as f:
            json.dump(new_glossary, f, indent=4, ensure_ascii=False)

        self.master.log(self.i18n.get("log_glossary_saved"))
        self.destroy()

    def on_close(self):
        # Poderia adicionar um aviso de "Salvar antes de fechar?" aqui
        self.destroy()

class TranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.i18n = I18nManager(language="pt_BR") # Começa em português
        self._carregar_idiomas_disponiveis()
        nome_amigavel_inicial = [name for name, code in self.idiomas_disponiveis.items() if code == self.i18n.language][0]
        self.language_variable = ctk.StringVar(value=nome_amigavel_inicial)
        self.api_key = self.carregar_ou_pedir_api_key()
        if not self.api_key:
            self.destroy()
            return

        self.title("Game XML Translator v1.1")
        self.geometry("1366x768")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.arquivo_xml_path = ""
        self.dados_traducao = {}
        self.cancel_event = threading.Event()

        self.modelos_disponiveis = {
            "Gemini 1.5 Flash (Rápido)": ("models/gemini-1.5-flash-latest", 5),
            "Gemini 2.5 Pro (Qualidade)": ("models/gemini-2.5-pro", 31)
        }
        self.modelo_selecionado = ctk.StringVar(value=list(self.modelos_disponiveis.keys())[0])

        self.left_sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.left_sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.left_sidebar_frame.grid_rowconfigure(8, weight=1)

        self.center_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.center_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.center_frame.grid_columnconfigure(0, weight=1)
        self.center_frame.grid_rowconfigure(0, weight=1)

        self.right_sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.right_sidebar_frame.grid(row=0, column=2, sticky="nsew")
        self.right_sidebar_frame.grid_rowconfigure(8, weight=1)

        # PAINEL ESQUERDO
        self.lang_optionmenu = ctk.CTkOptionMenu(
            self.left_sidebar_frame,
            variable=self.language_variable,
            values=list(self.idiomas_disponiveis.keys()),
            command=self.change_language,
        )
        self.lang_optionmenu.grid(row=3, column=0, padx=20, pady=10)

        self.project_label = ctk.CTkLabel(self.left_sidebar_frame, text=self.i18n.get("project_panel_title"), font=ctk.CTkFont(size=20, weight="bold"))
        self.project_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.load_xml_button = ctk.CTkButton(self.left_sidebar_frame, text=self.i18n.get("load_xml_button"), command=self.selecionar_arquivo_xml)
        self.load_xml_button.grid(row=1, column=0, padx=20, pady=10)

        self.glossary_button = ctk.CTkButton(self.left_sidebar_frame, text=self.i18n.get("manage_glossary_button"), command=self.open_glossary_window)
        self.glossary_button.grid(row=2, column=0, padx=20, pady=10)

        self.caminho_arquivo_entry = ctk.CTkEntry(self.left_sidebar_frame, placeholder_text=self.i18n.get("loaded_file_placeholder"))
        self.caminho_arquivo_entry.grid(row=4, column=0, padx=20, pady=(0, 20))
        self.caminho_arquivo_entry.configure(state="disabled")

        self.progress_label = ctk.CTkLabel(self.left_sidebar_frame, text=self.i18n.get("progress_label"), anchor="w")
        self.progress_label.grid(row=5, column=0, padx=20, pady=(10, 0))

        self.progressbar = ctk.CTkProgressBar(self.left_sidebar_frame, height=15)
        self.progressbar.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progressbar.set(0)

        self.stats_label = ctk.CTkLabel(self.left_sidebar_frame, text=self.i18n.get("stats_template"), anchor="w")
        self.stats_label.grid(row=7, column=0, padx=20, pady=(0, 20))

        self.export_button = ctk.CTkButton(self.left_sidebar_frame, text=self.i18n.get("export_button"), command=self.exportar_xml_traduzido)
        self.export_button.grid(row=9, column=0, padx=20, pady=20, sticky="s")

        # PAINEL CENTRAL
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2a2d2e", foreground="white", fieldbackground="#2a2d2e", borderwidth=0, rowheight=25)
        style.configure("Treeview.Heading", background="#565b5e", foreground="white", font=("Arial", 10, "bold"))
        style.map('Treeview.Heading', background=[('active', '#3484F0')])

        self.tree = ttk.Treeview(self.center_frame, columns=("Original", "Traducao"), show="headings")
        self.tree.heading("Original", text=self.i18n.get("original_text_label"))
        self.tree.heading("Traducao", text=self.i18n.get("translation_label"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.tree.tag_configure('traduzido', background='#1E4436')
        self.tree.tag_configure('traduzindo', background='#565b5e')

        scrollbar = ctk.CTkScrollbar(self.center_frame, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Mini-Terminal de Log
        self.log_textbox = ctk.CTkTextbox(self.center_frame, height=100)
        self.log_textbox.grid(row=1, column=0, columnspan=2, padx=0, pady=(5, 0), sticky="ew")
        self.log_textbox.configure(state="disabled", font=("Inter", 15))

        # PAINEL DIREITO
        self.tools_label = ctk.CTkLabel(self.right_sidebar_frame, text=self.i18n.get("tools_panel_title"), font=ctk.CTkFont(size=20, weight="bold"))
        self.tools_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10))

        # Seleção de Modelo
        self.model_label = ctk.CTkLabel(self.right_sidebar_frame, text=self.i18n.get("ai_model_label"), anchor="w")
        self.model_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(10, 0), sticky="w")

        self.model_optionmenu = ctk.CTkOptionMenu(self.right_sidebar_frame, variable=self.modelo_selecionado, values=list(self.modelos_disponiveis.keys()))
        self.model_optionmenu.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

        self.traduzir_tudo_button = ctk.CTkButton(self.right_sidebar_frame, text=self.i18n.get("translate_all_button"), command=self.iniciar_traducao_em_massa)
        self.traduzir_tudo_button.grid(row=3, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        self.original_textbox = ctk.CTkTextbox(self.right_sidebar_frame, height=100)
        self.original_textbox.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        self.original_textbox.configure(state="disabled")

        self.traducao_textbox = ctk.CTkTextbox(self.right_sidebar_frame, height=100)
        self.traducao_textbox.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")

        self.sugestao_button = ctk.CTkButton(self.right_sidebar_frame, text=self.i18n.get("generate_suggestion_button"), command=self.iniciar_traducao_linha_selecionada)
        self.sugestao_button.grid(row=6, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        self.aprovar_button = ctk.CTkButton(self.right_sidebar_frame, text=self.i18n.get("approve_button"), fg_color="green", hover_color="darkgreen", command=self.aprovar_traducao)
        self.aprovar_button.grid(row=9, column=0, columnspan=2, padx=20, pady=10, sticky="s")

        self.update_ui_texts()
        self.log(self.i18n.get("log_welcome"))

    def log(self, message):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_textbox.configure(state="disabled")
        self.log_textbox.see("end")

    def carregar_ou_pedir_api_key(self):
        config_path = "config.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("api_key")
        except (FileNotFoundError, json.JSONDecodeError):
            dialog = ctk.CTkInputDialog(text=self.i18n.get("api_gemini_key"), title=self.i18n.get("api_key_config"))
            key = dialog.get_input()
            if key:
                with open(config_path, 'w') as f:
                    json.dump({"api_key": key}, f)
                return key
        return None

    def selecionar_arquivo_xml(self):
        filepath = filedialog.askopenfilename(title=self.i18n.get("select_xml_file"), filetypes=(("Arquivos XML", "*.xml"), ("Todos os arquivos", "*.*")))
        if not filepath:
            return

        self.arquivo_xml_path = filepath
        filename = os.path.basename(filepath)
        self.caminho_arquivo_entry.configure(state="normal")
        self.caminho_arquivo_entry.delete(0, "end")
        self.caminho_arquivo_entry.insert(0, filename)
        self.caminho_arquivo_entry.configure(state="disabled")

        temp_json_path = "temp_extracao.json"
        if extrair_textos(self.arquivo_xml_path, temp_json_path):
            with open(temp_json_path, encoding='utf-8') as f:
                self.dados_traducao = json.load(f)
            os.remove(temp_json_path)

            for i in self.tree.get_children():
                self.tree.delete(i)

            for i, (original, traducao) in enumerate(self.dados_traducao.items()):
                self.tree.insert("", "end", iid=i, values=(original, traducao), tags=('nao_traduzido',))

            # A mágica acontece aqui, resetando e calculando o progresso inicial.
            self.atualizar_estatisticas()
            self.log(self.i18n.get("log_extract_success", count=len(self.dados_traducao)))
        else:
            self.log(self.i18n.get("log_extract_fail"))

    def change_language(self, language_choice: str):
        lang_code = self.idiomas_disponiveis.get(language_choice)
        if lang_code:
            self.i18n.load_language(lang_code)
            self.update_ui_texts()
            self.log(self.i18n.get("changed_language", lang_name=language_choice))

    def _carregar_idiomas_disponiveis(self):
        self.idiomas_disponiveis = {}
        locales_path = resource_path("locales")
        if not os.path.exists(locales_path):
            return

        for filename in os.listdir(locales_path):
            if filename.endswith(".json"):
                lang_code = filename.replace(".json", "")
                try:
                    with open(os.path.join(locales_path, filename), encoding='utf-8') as f:
                        data = json.load(f)
                        lang_name = data.get("_language_name", lang_code) # Usa o nome amigável ou o código do arquivo
                        self.idiomas_disponiveis[lang_name] = lang_code
                except Exception as e:
                    print(f"Erro ao carregar o idioma {filename}: {e}")

    def update_ui_texts(self):
        """
        Esta função é o "coração" da troca de idioma. Ela passa por todos
        os widgets e atualiza seus textos com base no novo idioma carregado.
        """
        self.title(self.i18n.get("window_title"))
        self.project_label.configure(text=self.i18n.get("project_panel_title"))
        self.load_xml_button.configure(text=self.i18n.get("load_xml_button"))
        self.glossary_button.configure(text=self.i18n.get("manage_glossary_button"))
        self.progress_label.configure(text=self.i18n.get("progress_label"))
        self.export_button.configure(text=self.i18n.get("export_button"))
        self.tools_label.configure(text=self.i18n.get("tools_panel_title"))
        self.model_label.configure(text=self.i18n.get("ai_model_label"))
        self.traduzir_tudo_button.configure(text=self.i18n.get("translate_all_button"))
        self.sugestao_button.configure(text=self.i18n.get("generate_suggestion_button"))
        self.tree.heading("Original", text=self.i18n.get("original_text_label"))
        self.tree.heading("Traducao", text=self.i18n.get("translation_label"))
        self.aprovar_button.configure(text=self.i18n.get("approve_button"))
        # Habilita o widget temporariamente para receber a configuração
        self.caminho_arquivo_entry.configure(state="normal")
        # Aplica o novo texto do placeholder
        self.caminho_arquivo_entry.configure(placeholder_text=self.i18n.get("loaded_file_placeholder"))
        # Desabilita o widget novamente para o usuário não poder editar
        self.caminho_arquivo_entry.configure(state="disabled")
        # ...e assim por diante para CADA widget que tem texto.
        self.atualizar_estatisticas() # Para atualizar o texto do stats_label

    def on_tree_select(self, event):
        if not self.tree.selection():
            return
        selected_item_id = self.tree.selection()[0]
        values = self.tree.item(selected_item_id, 'values')
        original_text = values[0]
        translation_text = values[1]
        self.original_textbox.configure(state="normal")
        self.original_textbox.delete("1.0", "end")
        self.original_textbox.insert("1.0", original_text)
        self.original_textbox.configure(state="disabled")
        self.traducao_textbox.delete("1.0", "end")
        self.traducao_textbox.insert("1.0", translation_text)

    def iniciar_traducao_linha_selecionada(self):
        if not self.tree.selection():
            self.log(self.i18n.get("log_no_selection"))
            return
        threading.Thread(target=self._worker_traduzir_linha, daemon=True).start()

    def _worker_traduzir_linha(self):
        selected_item_id = self.tree.selection()[0]
        original_text = self.tree.item(selected_item_id, 'values')[0]

        self.after(0, lambda: self.tree.item(selected_item_id, tags=('traduzindo',)))

        modelo_escolhido, _ = self.modelos_disponiveis[self.modelo_selecionado.get()]
        traducao_sugerida = traduzir_texto_unico(original_text, self.api_key, modelo_escolhido)

        self.after(0, lambda: self._update_ui_com_traducao(selected_item_id, traducao_sugerida))
        self.after(0, lambda: self.aprovar_traducao(id_item=selected_item_id, salvar_texto=False))

    def _worker_traducao_em_massa(self):
        ids_para_traduzir = [item_id for item_id in self.tree.get_children() if 'nao_traduzido' in self.tree.item(item_id, 'tags')]
        total_a_traduzir = len(ids_para_traduzir)
        self.log(self.i18n.get("log_mass_trans_found"))

        modelo_escolhido, pausa = self.modelos_disponiveis[self.modelo_selecionado.get()]

        for i, item_id in enumerate(ids_para_traduzir):
            if self.cancel_event.is_set():
                self.log(self.i18n.get("log_mass_trans_cancelled"))
                break

            self.after(0, lambda id=item_id: self.tree.see(id))
            self.after(0, lambda id=item_id: self.tree.item(id, tags=('traduzindo',)))
            original_text = self.tree.item(item_id, 'values')[0]
            self.log(f"({i+1}/{total_a_traduzir}) Traduzindo: '{original_text}'...")

            traducao_sugerida = traduzir_texto_unico(original_text, self.api_key, modelo_escolhido)

            if self.cancel_event.is_set():
                continue

            self.after(0, lambda id=item_id, trad=traducao_sugerida: self._update_ui_com_traducao(id, trad))
            self.after(0, lambda id=item_id: self.aprovar_traducao(id_item=id, salvar_texto=False))
            time.sleep(pausa)

        if not self.cancel_event.is_set():
            self.log(self.i18n.get("log_mass_trans_done"))

        # Reseta o botão para o estado original
        self.after(0, lambda: self.traduzir_tudo_button.configure(text=self.i18n.get("translate_all_button"), fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"], hover_color=ctk.ThemeManager.theme["CTkButton"]["hover_color"]))

    def iniciar_traducao_em_massa(self):
        if self.traduzir_tudo_button.cget("text") == self.i18n.get("cancel_button"):
            self.cancel_event.set()
            self.log(self.i18n.get("log_mass_trans_cancel_req"))
            return

        self.traduzir_tudo_button.configure(text=self.i18n.get("cancel_button"), fg_color="red", hover_color="darkred")
        self.cancel_event.clear()
        threading.Thread(target=self._worker_traducao_em_massa, daemon=True).start()

    def aprovar_traducao(self, id_item=None, salvar_texto=True):
        selected_item_id = id_item if id_item else (self.tree.selection()[0] if self.tree.selection() else None)
        if not selected_item_id:
            return

        tags_atuais = self.tree.item(selected_item_id, 'tags')
        original_text, traducao_antiga = self.tree.item(selected_item_id, 'values')

        nova_traducao = traducao_antiga
        if salvar_texto:
            nova_traducao = self.traducao_textbox.get("1.0", "end-1c").strip()

        # Atualiza a tabela com o novo valor e a nova tag
        self.tree.item(selected_item_id, values=(original_text, nova_traducao), tags=('traduzido',))

        # Só atualiza as estatísticas se o item era 'nao_traduzido' antes.
        # Isso evita contar o mesmo item duas vezes.
        if 'nao_traduzido' in tags_atuais:
            self.atualizar_estatisticas()

    def _update_textbox_com_feedback(self, item_id, texto):
        if self.tree.selection() and self.tree.selection()[0] == item_id:
            self.traducao_textbox.delete("1.0", "end")
            self.traducao_textbox.insert("1.0", texto)

    def _update_ui_com_traducao(self, item_id, traducao_sugerida):
        original_text = self.tree.item(item_id, 'values')[0]
        self.tree.item(item_id, values=(original_text, traducao_sugerida))
        if self.tree.selection() and self.tree.selection()[0] == item_id:
            self.traducao_textbox.delete("1.0", "end")
            self.traducao_textbox.insert("1.0", traducao_sugerida)

    def atualizar_estatisticas(self):
        # Lógica 100% baseada na contagem de tags, muito mais confiável.
        total_itens = len(self.tree.get_children())
        itens_traduzidos = len(self.tree.tag_has('traduzido'))

        self.stats_label.configure(text=self.i18n.get("stats_template", done=itens_traduzidos, total=total_itens))
        progresso = itens_traduzidos / total_itens if total_itens > 0 else 0
        self.progressbar.set(progresso)

    def exportar_xml_traduzido(self):
        """
        Coleta todas as traduções da tabela e gera o arquivo XML final.
        """
        # 1. Verifica se um arquivo foi carregado
        if not self.arquivo_xml_path:
            messagebox.showwarning(self.i18n.get("warn_no_xml_title"), self.i18n.get("warn_no_xml_message"))
            return

        # 2. Coleta todos os dados atuais da tabela (TreeView)
        mapa_final_traducoes = {}
        for child_id in self.tree.get_children():
            original, traducao = self.tree.item(child_id, 'values')
            mapa_final_traducoes[original] = traducao

        # 3. Pede ao usuário para escolher onde salvar o arquivo
        caminho_saida = filedialog.asksaveasfilename(
            title=self.i18n.get("save_as"),
            defaultextension=".xml",
            filetypes=(("Arquivos XML", "*.xml"), ("Todos os arquivos", "*.*")),
            initialfile=f"{os.path.basename(self.arquivo_xml_path).replace('.xml', '')}_traduzido.xml"
        )

        if not caminho_saida:
            print(self.i18n.get("export_cancelled"))
            return

        # 4. Chama nossa função injetora
        sucesso = injetar_traducoes(
            arquivo_xml_original=self.arquivo_xml_path,
            mapa_traducoes=mapa_final_traducoes,
            arquivo_xml_final=caminho_saida
        )

        # 5. Mostra uma mensagem de sucesso ou erro
        if sucesso:
            messagebox.showinfo("Sucesso", f"Arquivo XML traduzido salvo com sucesso em:\n{caminho_saida}")
        else:
            messagebox.showerror("Erro", self.i18n.get("export_fail"))

    def open_glossary_window(self):
        if hasattr(self, 'glossary_win') and self.glossary_win.winfo_exists():
            self.glossary_win.focus()
        else:
            self.glossary_win = GlossaryWindow(self)

# --- Ponto de Entrada da Aplicação ---
if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()
