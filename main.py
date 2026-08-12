import os
import re
import time
from threading import Thread

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.utils import platform

# Expresiones regulares para filtrado estricto
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
PHONE_REGEX = re.compile(r'^\+?[0-9\s\(\)\-]{7,20}$')
USER_REGEX  = re.compile(r'^[a-zA-Z0-9._\-]{3,32}$')

class ComboFilterUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=15, spacing=10, **kwargs)

        # Encabezado
        self.title_label = Label(
            text="[b]COMBO FILTER[/b]\n[size=14]by @ERICKSTREAM[/size]",
            markup=True,
            font_size='22sp',
            size_hint_y=None,
            height=60,
            halign='center'
        )
        self.add_widget(self.title_label)

        # Campo de Dominios
        self.add_widget(Label(text="Dominios a filtrar (separados por coma):", size_hint_y=None, height=25))
        self.domain_input = TextInput(
            text="disney.com, netflix.com",
            multiline=False,
            size_hint_y=None,
            height=40
        )
        self.add_widget(self.domain_input)

        # Botones de Acción
        btn_layout = BoxLayout(spacing=10, size_hint_y=None, height=50)
        self.btn_txt = Button(text="Filtrar /Txt", on_press=lambda x: self.start_process("txt"))
        self.btn_logs = Button(text="Filtrar /Logs", on_press=lambda x: self.start_process("logs"))
        self.btn_all = Button(text="Filtrar Todo", on_press=lambda x: self.start_process("all"))

        btn_layout.add_widget(self.btn_txt)
        btn_layout.add_widget(self.btn_logs)
        btn_layout.add_widget(self.btn_all)
        self.add_widget(btn_layout)

        # Barra de Progreso
        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=20)
        self.add_widget(self.progress_bar)

        # Consola de Estado / Log
        self.add_widget(Label(text="Estado de la Operación:", size_hint_y=None, height=25))
        self.log_output = TextInput(
            text="Listo para iniciar...\nColoca tus carpetas Txt o Logs en la memoria interna.\n",
            readonly=True,
            multiline=True
        )
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.log_output)
        self.add_widget(scroll)

        # Solicitar permisos en Android al iniciar
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

    def append_log(self, text):
        Clock.schedule_once(lambda dt: self._update_log(text))

    def _update_log(self, text):
        self.log_output.text += text + "\n"

    def update_progress(self, val, total):
        Clock.schedule_once(lambda dt: self._set_progress(val, total))

    def _set_progress(self, val, total):
        self.progress_bar.max = total if total > 0 else 1
        self.progress_bar.value = val

    def start_process(self, mode):
        # Deshabilitar botones mientras procesa
        self.btn_txt.disabled = True
        self.btn_logs.disabled = True
        self.btn_all.disabled = True
        self.log_output.text = "Iniciando escaneo...\n"

        # Ejecutar en hilo secundario para no congelar la app
        Thread(target=self.run_filter_engine, args=(mode,), daemon=True).start()

    def run_filter_engine(self, mode):
        domains = [d.strip().lower() for d in self.domain_input.text.split(",") if d.strip()]
        if not domains:
            self.append_log("[!] Debes ingresar al menos un dominio objetivo.")
            self.enable_buttons()
            return

        # Determinar directorio base según la plataforma
        base_path = "/sdcard/ComboFilter" if platform == 'android' else os.getcwd()
        os.makedirs(base_path, exist_ok=True)

        files_to_process = []

        if mode in ["txt", "all"]:
            txt_dir = os.path.join(base_path, "Txt")
            os.makedirs(txt_dir, exist_ok=True)
            for f in os.listdir(txt_dir):
                if f.endswith(".txt"):
                    files_to_process.append(os.path.join(txt_dir, f))

        if mode in ["logs", "all"]:
            logs_dir = os.path.join(base_path, "Logs")
            os.makedirs(logs_dir, exist_ok=True)
            for root, _, files in os.walk(logs_dir):
                for f in files:
                    if f.lower() in ["passwords.txt", "password.txt", "pass.txt"]:
                        files_to_process.append(os.path.join(root, f))

        if not files_to_process:
            self.append_log(f"[!] No se encontraron archivos para procesar en '{base_path}'.")
            self.enable_buttons()
            return

        self.append_log(f"[+] Archivos detectados: {len(files_to_process)}")
        self.append_log(f"[+] Objetivos: {', '.join(domains)}\n")

        results = {d: set() for d in domains}
        total_lines = 0
        total_hits = 0
        start_time = time.time()

        for idx, file_path in enumerate(files_to_process, 1):
            file_name = os.path.basename(file_path)
            self.append_log(f"-> Leyendo [{idx}/{len(files_to_process)}]: {file_name}")
            self.update_progress(idx, len(files_to_process))

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        total_lines += 1
                        line_str = line.strip()
                        if not line_str or '",' in line_str or '{"' in line_str:
                            continue

                        # Limpieza de comillas
                        line_str = re.sub(r'^["\']|["\']$', '', line_str)
                        line_str = re.sub(r'^["\'](.*?)["\']\s*:\s*["\'](.*?)["\']$', r'\1:\2', line_str)

                        parts = line_str.split(":")
                        if len(parts) >= 2:
                            user_part = parts[-2] if len(parts) >= 3 else parts[0]
                            pass_part = parts[-1]

                            # Validar credencial
                            user_clean = user_part.strip(' "\'\t\r\n\\')
                            pass_clean = pass_part.strip(' "\'\t\r\n\\')

                            if user_clean and pass_clean and len(pass_clean) >= 2:
                                for d in domains:
                                    if f"@{d}" in user_clean.lower() or d in user_clean.lower() or (len(parts) >= 3 and d in parts[0].lower()):
                                        # Identificar formato
                                        if EMAIL_REGEX.match(user_clean):
                                            combo = f"{user_clean.lower()}:{pass_clean}"
                                        elif PHONE_REGEX.match(user_clean):
                                            combo = f"{re.sub(r'[^\d+]', '', user_clean)}:{pass_clean}"
                                        elif USER_REGEX.match(user_clean):
                                            combo = f"{user_clean}:{pass_clean}"
                                        else:
                                            combo = None

                                        if combo:
                                            results[d].add(combo)
                                            total_hits += 1
            except Exception as e:
                self.append_log(f"[!] Error leyendo {file_name}: {e}")

        elapsed = time.time() - start_time
        self.append_log("\n" + "="*40)
        self.append_log(">>> PROCESO FINALIZADO <<<")
        self.append_log(f"• Tiempo: {elapsed:.2f} segundos")
        self.append_log(f"• Líneas leídas: {total_lines:,}")
        self.append_log(f"• Hits limpios: {total_hits:,}\n")

        # Guardar en almacenamiento
        for d, combos in results.items():
            out_file = os.path.join(base_path, f"{d}.txt")
            with open(out_file, "w", encoding="utf-8") as out_f:
                for c in sorted(combos):
                    out_f.write(f"{c}\n")
            self.append_log(f"[✓] Guardado -> {d}.txt ({len(combos):,} combos)")

        self.enable_buttons()

    def enable_buttons(self):
        Clock.schedule_once(lambda dt: self._reset_buttons())

    def _reset_buttons(self):
        self.btn_txt.disabled = False
        self.btn_logs.disabled = False
        self.btn_all.disabled = False

class ComboFilterApp(App):
    def build(self):
        self.title = "Combo Filter - @ERICKSTREAM"
        return ComboFilterUI()

if __name__ == "__main__":
    ComboFilterApp().run()
