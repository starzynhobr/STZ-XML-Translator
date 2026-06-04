import json
import os
import queue
import sys
import threading
import time

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

from core.app_controller import AppController, resource_path
from core.i18n import I18nManager
from core.tradutor_api import list_gemini_models

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ---------------------------------------------------------------------------
# Glossary window — pure UI, reads/writes glossario.json directly
# ---------------------------------------------------------------------------

class GlossaryWindow(ctk.CTkToplevel):
    def __init__(self, master: "TranslatorApp") -> None:
        super().__init__(master)
        self.transient(master)
        self.i18n = master.i18n
        self.title(self.i18n.get("glossary_window_title"))
        self.geometry("600x400")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._glossary_path = resource_path(os.path.join("scripts", "glossario.json"))
        self._data = self._load()
        self._entries: list[tuple[ctk.CTkEntry, ctk.CTkEntry]] = []

        self._scrollable = ctk.CTkScrollableFrame(self, label_text=self.i18n.get("glossary_terms_label"))
        self._scrollable.pack(expand=True, fill="both", padx=10, pady=10)
        self._rebuild()

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text=self.i18n.get("glossary_add_button"), command=self._add_row).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text=self.i18n.get("glossary_save_button"), command=self._save_and_close).pack(side="right", padx=5)

    def _load(self) -> dict:
        if os.path.exists(self._glossary_path):
            with open(self._glossary_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _rebuild(self) -> None:
        for widget in self._scrollable.winfo_children():
            widget.destroy()
        self._entries = []
        for i, (key, value) in enumerate(self._data.items()):
            self._create_row(i, key, value)

    def _create_row(self, index: int, key: str, value: str) -> None:
        key_e = ctk.CTkEntry(self._scrollable)
        key_e.insert(0, key)
        key_e.grid(row=index, column=0, padx=5, pady=5, sticky="ew")
        val_e = ctk.CTkEntry(self._scrollable)
        val_e.insert(0, value)
        val_e.grid(row=index, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(
            self._scrollable, text="X", width=20,
            fg_color="red", hover_color="darkred",
            command=lambda i=index: self._delete_row(i),
        ).grid(row=index, column=2, padx=5, pady=5)
        self._entries.append((key_e, val_e))
        self._scrollable.grid_columnconfigure(0, weight=1)
        self._scrollable.grid_columnconfigure(1, weight=1)

    def _add_row(self) -> None:
        self._create_row(len(self._entries), "", "")

    def _delete_row(self, index: int) -> None:
        self._data.pop(list(self._data.keys())[index])
        self._rebuild()

    def _save_and_close(self) -> None:
        new_data = {
            k.get().strip(): v.get().strip()
            for k, v in self._entries
            if k.get().strip() and v.get().strip()
        }
        with open(self._glossary_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)
        self.master.log(self.i18n.get("log_glossary_saved"))
        self.destroy()


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class TranslatorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.ctrl = AppController()
        self.i18n = I18nManager(language="pt_BR")
        self._translation_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._glossary_win: GlossaryWindow | None = None

        # Model state managed in UI layer (labels ↔ IDs)
        self.modelos_disponiveis: dict[str, tuple[str, int]] = {
            "Gemini 1.5 Flash (Rapido)": ("gemini-1.5-flash", 5),
            "Gemini 1.5 Pro (Qualidade)": ("gemini-1.5-pro", 31),
        }
        self.modelo_selecionado = ctk.StringVar(value=list(self.modelos_disponiveis.keys())[0])

        # Restore preferred model from saved config
        if self.ctrl.preferred_model_label and self.ctrl.preferred_model_label in self.modelos_disponiveis:
            self.modelo_selecionado.set(self.ctrl.preferred_model_label)
        elif self.ctrl.preferred_model_id:
            for label, (mid, _) in self.modelos_disponiveis.items():
                if mid == self.ctrl.preferred_model_id:
                    self.modelo_selecionado.set(label)
                    break

        # UI locale
        self._idiomas_disponiveis = self.ctrl.available_locales()
        self.ctrl.set_translation_target(self.i18n.language)
        _initial_lang = next(
            (name for name, code in self._idiomas_disponiveis.items() if code == self.i18n.language),
            list(self._idiomas_disponiveis.keys())[0],
        )
        self.language_variable = ctk.StringVar(value=_initial_lang)

        # Window setup
        self.title("Game XML Translator")
        self.geometry("1200x700")
        self.minsize(1000, 600)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1, minsize=400)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

        self.update_ui_texts()
        self.log(self.i18n.get("log_welcome"))
        if self.ctrl.api_key:
            self.after(200, self._sincronizar_modelos)

    # ------------------------------------------------------------------
    # Panel builders
    # ------------------------------------------------------------------

    def _build_left_panel(self) -> None:
        f = ctk.CTkFrame(self, corner_radius=0, width=320)
        f.grid(row=0, column=0, sticky="nsw", padx=(5, 2), pady=5)
        f.grid_rowconfigure(14, weight=1)
        f.grid_propagate(False)
        self._left = f

        self.project_label = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.project_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.load_xml_button = ctk.CTkButton(f, text="", command=self._selecionar_xml)
        self.load_xml_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.glossary_button = ctk.CTkButton(f, text="", command=self._open_glossary)
        self.glossary_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        io = ctk.CTkFrame(f)
        io.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        io.grid_columnconfigure((0, 1), weight=1)
        self.export_json_button = ctk.CTkButton(io, text="", command=self._exportar_json)
        self.export_json_button.grid(row=0, column=0, padx=(5, 2), pady=(5, 2), sticky="ew")
        self.export_csv_button = ctk.CTkButton(io, text="", command=self._exportar_csv)
        self.export_csv_button.grid(row=0, column=1, padx=(2, 5), pady=(5, 2), sticky="ew")
        self.import_json_button = ctk.CTkButton(io, text="", command=self._importar_json)
        self.import_json_button.grid(row=1, column=0, padx=(5, 2), pady=(2, 5), sticky="ew")
        self.import_csv_button = ctk.CTkButton(io, text="", command=self._importar_csv)
        self.import_csv_button.grid(row=1, column=1, padx=(2, 5), pady=(2, 5), sticky="ew")

        self.lang_optionmenu = ctk.CTkOptionMenu(
            f, variable=self.language_variable,
            values=list(self._idiomas_disponiveis.keys()),
            command=self._change_language,
        )
        self.lang_optionmenu.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.caminho_arquivo_entry = ctk.CTkEntry(f, placeholder_text="")
        self.caminho_arquivo_entry.grid(row=5, column=0, padx=20, pady=(10, 10), sticky="ew")

        self.tag_alvo_label = ctk.CTkLabel(f, text="")
        self.tag_alvo_label.grid(row=6, column=0, padx=20, pady=(10, 2))
        self.tag_alvo_entry = ctk.CTkEntry(f)
        self.tag_alvo_entry.insert(0, "bio")
        self.tag_alvo_entry.grid(row=7, column=0, padx=40, pady=(0, 20))

        self.parent_tag_label = ctk.CTkLabel(f, text="")
        self.parent_tag_label.grid(row=8, column=0, padx=20, pady=(10, 2))
        self.parent_tag_entry = ctk.CTkEntry(f)
        self.parent_tag_entry.insert(0, "baseVillain")
        self.parent_tag_entry.grid(row=9, column=0, padx=40, pady=(0, 10))

        self.reload_button = ctk.CTkButton(f, text="", command=self._recarregar_xml, state="disabled")
        self.reload_button.grid(row=10, column=0, padx=40, pady=(0, 20), sticky="ew")

        self.progress_label = ctk.CTkLabel(f, text="")
        self.progress_label.grid(row=11, column=0, padx=20, pady=(10, 2))
        self.progressbar = ctk.CTkProgressBar(f, height=15)
        self.progressbar.grid(row=12, column=0, padx=40, pady=(0, 2))
        self.stats_label = ctk.CTkLabel(f, text="")
        self.stats_label.grid(row=13, column=0, padx=20, pady=(0, 20))

        self.export_button = ctk.CTkButton(f, text="", command=self._exportar_xml)
        self.export_button.grid(row=15, column=0, padx=20, pady=10, sticky="ew")

    def _build_center_panel(self) -> None:
        f = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        f.grid(row=0, column=1, sticky="nsew", padx=2, pady=5)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2a2d2e", foreground="white",
                         fieldbackground="#2a2d2e", borderwidth=0, rowheight=25)
        style.configure("Treeview.Heading", background="#565b5e", foreground="white",
                         font=("Arial", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", "#3484F0")])

        self.tree = ttk.Treeview(f, columns=("Original", "Traducao"), show="headings")
        self.tree.heading("Original", text="")
        self.tree.heading("Traducao", text="")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.tag_configure("traduzido", background="#1E4436")
        self.tree.tag_configure("traduzindo", background="#565b5e")

        scrollbar = ctk.CTkScrollbar(f, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.log_textbox = ctk.CTkTextbox(f, height=100, font=("Inter", 15))
        self.log_textbox.grid(row=1, column=0, columnspan=2, padx=0, pady=(5, 0), sticky="ew")
        self.log_textbox.configure(state="disabled")

    def _build_right_panel(self) -> None:
        f = ctk.CTkFrame(self, corner_radius=0, width=330)
        f.grid(row=0, column=2, sticky="nsew", padx=(2, 5), pady=5)
        f.grid_rowconfigure(8, weight=1)
        f.grid_columnconfigure(0, weight=1)
        f.grid_propagate(False)

        self.tools_label = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.tools_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.model_label = ctk.CTkLabel(f, text="", anchor="w")
        self.model_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")

        self.model_optionmenu = ctk.CTkOptionMenu(
            f, variable=self.modelo_selecionado,
            values=list(self.modelos_disponiveis.keys()),
            command=self._on_model_change,
        )
        self.model_optionmenu.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.api_button = ctk.CTkButton(f, text="", command=self._configurar_api_key)
        self.api_button.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.traduzir_tudo_button = ctk.CTkButton(f, text="", command=self._iniciar_ou_cancelar_lote)
        self.traduzir_tudo_button.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.original_textbox = ctk.CTkTextbox(f, height=100, state="disabled")
        self.original_textbox.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.traducao_textbox = ctk.CTkTextbox(f, height=100)
        self.traducao_textbox.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="ew")

        self.sugestao_button = ctk.CTkButton(f, text="", command=self._traduzir_linha)
        self.sugestao_button.grid(row=7, column=0, padx=20, pady=10, sticky="ew")

        self.aprovar_button = ctk.CTkButton(
            f, text="", fg_color="green", hover_color="darkgreen",
            command=self._aprovar_traducao,
        )
        self.aprovar_button.grid(row=9, column=0, padx=20, pady=10, sticky="s")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message: str) -> None:
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_textbox.configure(state="disabled")
        self.log_textbox.see("end")

    # ------------------------------------------------------------------
    # UI text sync (i18n)
    # ------------------------------------------------------------------

    def update_ui_texts(self) -> None:
        self.title(self.i18n.get("window_title"))
        self.project_label.configure(text=self.i18n.get("project_panel_title"))
        self.load_xml_button.configure(text=self.i18n.get("load_xml_button"))
        self.glossary_button.configure(text=self.i18n.get("manage_glossary_button"))
        self.import_json_button.configure(text=self.i18n.get("import_json_button"))
        self.import_csv_button.configure(text=self.i18n.get("import_csv_button"))
        self.export_json_button.configure(text=self.i18n.get("export_json_button"))
        self.export_csv_button.configure(text=self.i18n.get("export_csv_button"))
        self.caminho_arquivo_entry.configure(placeholder_text=self.i18n.get("loaded_file_placeholder"))
        self.tag_alvo_label.configure(text=self.i18n.get("target_tag_label"))
        self.parent_tag_label.configure(text=self.i18n.get("parent_tag_label"))
        self.reload_button.configure(text=self.i18n.get("reload_button"))
        self.progress_label.configure(text=self.i18n.get("progress_label"))
        self.export_button.configure(text=self.i18n.get("export_button"))
        self.tree.heading("Original", text=self.i18n.get("original_text_label"))
        self.tree.heading("Traducao", text=self.i18n.get("translation_label"))
        self.tools_label.configure(text=self.i18n.get("tools_panel_title"))
        self.model_label.configure(text=self.i18n.get("ai_model_label"))
        self.api_button.configure(text=self.i18n.get("api_key_config"))
        cancel_texts = {
            self.i18n.get("cancel_button"),
            self.i18n.get("cancelling_button"),
            self.i18n.get("translating_button"),
        }
        if self.traduzir_tudo_button.cget("text") not in cancel_texts:
            self.traduzir_tudo_button.configure(text=self.i18n.get("translate_all_button"))
        self.sugestao_button.configure(text=self.i18n.get("generate_suggestion_button"))
        self.aprovar_button.configure(text=self.i18n.get("approve_button"))
        self._atualizar_estatisticas()

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------

    def _populate_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for xpath, entry in self.ctrl.project.entries.items():
            tag = "traduzido" if entry.status == "done" else "nao_traduzido"
            self.tree.insert("", "end", iid=xpath, values=(entry.original, entry.translation), tags=(tag,))

    def _atualizar_estatisticas(self) -> None:
        done, total = self.ctrl.project.stats()
        self.stats_label.configure(text=self.i18n.get("stats_template", done=done, total=total))
        self.progressbar.set(done / total if total else 0)

    def _on_tree_select(self, _event: object) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        original, translation = self.tree.item(sel[0], "values")
        self.original_textbox.configure(state="normal")
        self.original_textbox.delete("1.0", "end")
        self.original_textbox.insert("1.0", original)
        self.original_textbox.configure(state="disabled")
        self.traducao_textbox.delete("1.0", "end")
        self.traducao_textbox.insert("1.0", translation)

    # ------------------------------------------------------------------
    # XML loading
    # ------------------------------------------------------------------

    def _selecionar_xml(self) -> None:
        path = filedialog.askopenfilename(
            title=self.i18n.get("select_xml_file"),
            filetypes=(("Arquivos XML", "*.xml"), ("Todos os arquivos", "*.*")),
        )
        if not path:
            return
        self.caminho_arquivo_entry.configure(state="normal")
        self.caminho_arquivo_entry.delete(0, "end")
        self.caminho_arquivo_entry.insert(0, os.path.basename(path))
        self.caminho_arquivo_entry.configure(state="disabled")
        self._carregar_xml(path)

    def _recarregar_xml(self) -> None:
        if not self.ctrl.project.xml_path or not os.path.exists(self.ctrl.project.xml_path):
            self.log("Nenhum arquivo válido carregado.")
            return
        self.log("Recarregando...")
        self._carregar_xml(self.ctrl.project.xml_path)

    def _carregar_xml(self, path: str) -> None:
        tag_alvo = self.tag_alvo_entry.get().strip()
        tag_pai = self.parent_tag_entry.get().strip()
        if not tag_alvo or not tag_pai:
            messagebox.showwarning("Atenção", "Especifique Tag Alvo e Tag Pai.")
            return
        sucesso, erro = self.ctrl.load_xml(path, tag_pai, tag_alvo)
        if sucesso:
            self._populate_tree()
            count = len(self.ctrl.project.entries)
            self.log(f"'{os.path.basename(path)}' carregado com {count} itens.")
            self.reload_button.configure(state="normal")
        else:
            self.log(erro)
        self._atualizar_estatisticas()

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def _exportar_xml(self) -> None:
        if not self.ctrl.project.xml_path:
            messagebox.showwarning(self.i18n.get("warn_no_xml_title"), self.i18n.get("warn_no_xml_message"))
            return
        if not self.ctrl.project.get_translations_map():
            messagebox.showwarning(self.i18n.get("warn_no_xml_title"), self.i18n.get("warn_no_translations_to_export"))
            return
        path = filedialog.asksaveasfilename(
            title=self.i18n.get("save_as"),
            defaultextension=".xml",
            filetypes=(("Arquivos XML", "*.xml"), ("Todos os arquivos", "*.*")),
            initialfile=os.path.basename(self.ctrl.project.xml_path).replace(".xml", "_traduzido.xml"),
        )
        if not path:
            return
        if self.ctrl.export_xml(path):
            messagebox.showinfo("Sucesso", f"XML salvo em:\n{path}")
            self.log("Exportação bem-sucedida.")
        else:
            messagebox.showerror("Erro", self.i18n.get("export_fail"))

    def _exportar_json(self) -> None:
        if not self.ctrl.project.xml_path:
            messagebox.showwarning(self.i18n.get("warn_no_xml_title"), self.i18n.get("warn_no_xml_message"))
            return
        path = filedialog.asksaveasfilename(
            title="Salvar JSON para Tradução",
            defaultextension=".json",
            filetypes=(("Arquivos JSON", "*.json"), ("Todos os arquivos", "*.*")),
            initialfile="textos_para_traduzir.json",
        )
        if not path:
            return
        if self.ctrl.export_json(path):
            messagebox.showinfo("Sucesso", f"JSON salvo em:\n{path}")
            self.log("JSON exportado.")
        else:
            messagebox.showerror("Erro de Gravação", "Não foi possível salvar o arquivo JSON.")

    def _exportar_csv(self) -> None:
        if not self.tree.get_children():
            messagebox.showwarning("Atenção", "Não há dados na tabela para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Salvar como CSV",
            defaultextension=".csv",
            filetypes=(("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")),
            initialfile="traducoes.csv",
        )
        if not path:
            return
        if self.ctrl.export_csv(path):
            messagebox.showinfo("Sucesso", f"CSV salvo em:\n{path}")
            self.log(f"CSV exportado: {os.path.basename(path)}")
        else:
            messagebox.showerror("Erro de Gravação", "Não foi possível salvar o arquivo CSV.")

    def _importar_json(self) -> None:
        if not self.tree.get_children():
            messagebox.showwarning("Atenção", "Carregue um XML primeiro.")
            return
        path = filedialog.askopenfilename(
            title="Selecione o JSON com traduções",
            filetypes=(("Arquivos JSON", "*.json"), ("Todos os arquivos", "*.*")),
        )
        if not path:
            return
        count = self.ctrl.import_json(path)
        self._populate_tree()
        self._atualizar_estatisticas()
        self.log(self.i18n.get("log_items_updated", count=count))
        if count:
            messagebox.showinfo(self.i18n.get("info_success_title"), self.i18n.get("info_translations_imported", count=count))
        else:
            messagebox.showwarning("Atenção", self.i18n.get("warn_no_matches_found"))

    def _importar_csv(self) -> None:
        if not self.tree.get_children():
            messagebox.showwarning("Atenção", "Carregue um XML primeiro.")
            return
        path = filedialog.askopenfilename(
            title="Selecione o CSV com traduções",
            filetypes=(("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")),
        )
        if not path:
            return
        count = self.ctrl.import_csv(path)
        self._populate_tree()
        self._atualizar_estatisticas()
        self.log(f"{count} itens atualizados do CSV.")
        if count:
            messagebox.showinfo("Sucesso", f"{count} traduções importadas do CSV.")
        else:
            messagebox.showwarning("Atenção", "Nenhuma tradução correspondente encontrada no CSV.")

    # ------------------------------------------------------------------
    # Config / API key
    # ------------------------------------------------------------------

    def _configurar_api_key(self) -> None:
        self._ensure_api_key(force=True)

    def _ensure_api_key(self, force: bool = False) -> bool:
        if self.ctrl.api_key and not force:
            return True
        dialog = ctk.CTkInputDialog(text=self.i18n.get("api_gemini_key"), title=self.i18n.get("api_key_config"))
        key = dialog.get_input()
        if key:
            label = self.modelo_selecionado.get()
            mid, _ = self.modelos_disponiveis.get(label, (self.ctrl.preferred_model_id, 0))
            self.ctrl.save_config(api_key=key.strip(), model_label=label, model_id=mid)
            self._sincronizar_modelos()
            self.log("Chave de API configurada com sucesso.")
            return True
        if not force:
            self.log(self.i18n.get("log_api_key_needed"))
        return False

    def _on_model_change(self, label: str) -> None:
        if label in self.modelos_disponiveis:
            mid, _ = self.modelos_disponiveis[label]
            self.ctrl.save_config(api_key=self.ctrl.api_key, model_label=label, model_id=mid)

    def _sincronizar_modelos(self) -> None:
        if not self.ctrl.api_key:
            return

        def worker() -> None:
            try:
                modelos_map = list_gemini_models(self.ctrl.api_key)
                if not modelos_map:
                    raise RuntimeError("Nenhum modelo Gemini encontrado.")
            except Exception as exc:
                self.after(0, lambda: self.log(f"Falha ao listar modelos Gemini: {exc}"))
                return

            def update_ui() -> None:
                self.modelos_disponiveis = modelos_map
                valores = list(modelos_map.keys())
                self.model_optionmenu.configure(values=valores)
                selecionado = next(
                    (lbl for lbl, (mid, _) in modelos_map.items() if mid == self.ctrl.preferred_model_id),
                    valores[0],
                )
                self.modelo_selecionado.set(selecionado)
                mid, _ = modelos_map[selecionado]
                self.ctrl.save_config(api_key=self.ctrl.api_key, model_label=selecionado, model_id=mid)
                self.log(f"Modelos Gemini carregados ({len(valores)})")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Translation — single entry
    # ------------------------------------------------------------------

    def _traduzir_linha(self) -> None:
        if not self._ensure_api_key():
            return
        sel = self.tree.selection()
        if not sel:
            self.log(self.i18n.get("log_no_selection"))
            return
        xpath = sel[0]
        self.tree.item(xpath, tags=("traduzindo",))
        config = self.ctrl.build_translation_config(self.modelo_selecionado.get(), self.modelos_disponiveis)

        def worker() -> None:
            result = self.ctrl.translate_single(xpath, config)
            self.after(0, lambda: self._apply_single_translation(xpath, result))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_single_translation(self, xpath: str, translation: str) -> None:
        self.ctrl.project.set_translation(xpath, translation)
        if self.tree.exists(xpath):
            original, _ = self.tree.item(xpath, "values")
            self.tree.item(xpath, values=(original, translation), tags=("traduzido",))
        if self.tree.selection() and self.tree.selection()[0] == xpath:
            self.traducao_textbox.delete("1.0", "end")
            self.traducao_textbox.insert("1.0", translation)
        self._atualizar_estatisticas()

    # ------------------------------------------------------------------
    # Translation — batch
    # ------------------------------------------------------------------

    def _iniciar_ou_cancelar_lote(self) -> None:
        if self.ctrl.is_translating():
            self.log("Solicitando cancelamento...")
            self.ctrl.cancel_translation()
            self.traduzir_tudo_button.configure(state="disabled", text=self.i18n.get("cancelling_button"))
            return

        if not self._ensure_api_key():
            return

        self.traduzir_tudo_button.configure(
            state="normal", text=self.i18n.get("cancel_button"),
            fg_color="red", hover_color="darkred",
        )
        config = self.ctrl.build_translation_config(self.modelo_selecionado.get(), self.modelos_disponiveis)

        def on_entry(xpath: str, text: str) -> None:
            self._translation_queue.put((xpath, text))

        def on_log(msg: str) -> None:
            self.after(0, lambda: self.log(msg))

        def on_done() -> None:
            self._translation_queue.put(("__DONE__", ""))

        self.ctrl.start_batch_translation(config, on_entry, on_log, on_done)
        self._processar_fila()

    def _processar_fila(self) -> None:
        try:
            while True:
                xpath, text = self._translation_queue.get_nowait()
                if xpath == "__DONE__":
                    self.traduzir_tudo_button.configure(
                        state="normal", text=self.i18n.get("translate_all_button"),
                        fg_color=["#3B8ED0", "#1F6AA5"], hover_color=["#36719F", "#144870"],
                    )
                    return
                if self.tree.exists(xpath):
                    original, _ = self.tree.item(xpath, "values")
                    self.tree.item(xpath, values=(original, text), tags=("traduzido",))
                self._atualizar_estatisticas()
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    # ------------------------------------------------------------------
    # Approve translation
    # ------------------------------------------------------------------

    def _aprovar_traducao(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        xpath = sel[0]
        nova = self.traducao_textbox.get("1.0", "end-1c").strip()
        old_tags = self.tree.item(xpath, "tags")
        self.ctrl.project.set_translation(xpath, nova)
        original, _ = self.tree.item(xpath, "values")
        self.tree.item(xpath, values=(original, nova), tags=("traduzido",))
        if "nao_traduzido" in old_tags:
            self._atualizar_estatisticas()

    # ------------------------------------------------------------------
    # Language switch
    # ------------------------------------------------------------------

    def _change_language(self, lang_name: str) -> None:
        code = self._idiomas_disponiveis.get(lang_name)
        if code:
            self.i18n.load_language(code)
            self.ctrl.set_translation_target(code)
            self.update_ui_texts()
            self.log(self.i18n.get("changed_language", lang_name=lang_name))

    # ------------------------------------------------------------------
    # Glossary window
    # ------------------------------------------------------------------

    def _open_glossary(self) -> None:
        if self._glossary_win and self._glossary_win.winfo_exists():
            self._glossary_win.focus()
        else:
            self._glossary_win = GlossaryWindow(self)


if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()
