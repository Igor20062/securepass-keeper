# main.py - SecurePass Keeper для Android
import sqlite3
import hashlib
import secrets
import base64
import os
from datetime import datetime
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock

# ==================== ТВОЯ КРИПТОГРАФИЯ ====================
try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except:
    CRYPTO_AVAILABLE = False

class CryptoManager:
    def __init__(self):
        self.cipher = None
    
    def initialize(self, key):
        if CRYPTO_AVAILABLE:
            self.cipher = Fernet(key)
        return True
    
    def generate_master_key(self):
        if CRYPTO_AVAILABLE:
            return Fernet.generate_key()
        return os.urandom(32)
    
    def encrypt(self, text):
        if not text or not self.cipher:
            return text
        return self.cipher.encrypt(text.encode()).decode()
    
    def decrypt(self, text):
        if not text or not self.cipher:
            return text
        return self.cipher.decrypt(text.encode()).decode()

# ==================== ТВОЙ КЛАСС ПОЛЬЗОВАТЕЛЕЙ ====================
class UserManager:
    def __init__(self):
        self.conn = sqlite3.connect("users.db")
        self.crypto = CryptoManager()
        self.init_db()
    
    def init_db(self):
        self.conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            salt TEXT,
            encrypted_master_key TEXT,
            created_at TEXT
        )''')
        self.conn.commit()
    
    def register_user(self, username, password):
        try:
            master_key = self.crypto.generate_master_key()
            salt = secrets.token_hex(16)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
            enc_key = base64.b64encode(master_key).decode()
            
            self.conn.execute(
                "INSERT INTO users (username, password_hash, salt, encrypted_master_key, created_at) VALUES (?,?,?,?,?)",
                (username, pwd_hash, salt, enc_key, datetime.now().isoformat())
            )
            self.conn.commit()
            return True
        except:
            return False
    
    def login_user(self, username, password):
        row = self.conn.execute(
            "SELECT password_hash, salt, encrypted_master_key FROM users WHERE username=?",
            (username,)
        ).fetchone()
        
        if not row:
            return False, None
        
        stored_hash, salt, enc_key = row
        input_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
        
        if input_hash == stored_hash:
            master_key = base64.b64decode(enc_key)
            return True, master_key
        return False, None
    
    def close(self):
        if self.conn:
            self.conn.close()

# ==================== ТВОЙ КЛАСС ПАРОЛЕЙ ====================
class PasswordDatabase:
    def __init__(self, username, master_key):
        self.db_file = f"passwords_{username}.db"
        self.crypto = CryptoManager()
        self.crypto.initialize(master_key)
        self.conn = sqlite3.connect(self.db_file)
        self.init_db()
    
    def init_db(self):
        self.conn.execute('''CREATE TABLE IF NOT EXISTS passwords (
            id INTEGER PRIMARY KEY,
            site TEXT NOT NULL,
            login TEXT NOT NULL,
            current_password TEXT NOT NULL,
            category TEXT DEFAULT 'Сайты',
            created_at TEXT,
            updated_at TEXT,
            comment TEXT
        )''')
        self.conn.commit()
    
    def add_password(self, site, login, password, category="Сайты", comment=""):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO passwords (site, login, current_password, category, created_at, updated_at, comment) VALUES (?,?,?,?,?,?,?)",
            (self.crypto.encrypt(site), self.crypto.encrypt(login), self.crypto.encrypt(password),
             category, now, now, self.crypto.encrypt(comment))
        )
        self.conn.commit()
    
    def get_all_passwords(self):
        rows = self.conn.execute(
            "SELECT id, site, login, current_password, category, updated_at, comment FROM passwords ORDER BY updated_at DESC"
        ).fetchall()
        
        passwords = []
        for row in rows:
            try:
                passwords.append({
                    'id': row[0],
                    'site': self.crypto.decrypt(row[1]),
                    'login': self.crypto.decrypt(row[2]),
                    'password': self.crypto.decrypt(row[3]),
                    'category': row[4],
                    'updated_at': row[5][:16] if row[5] else "",
                    'comment': self.crypto.decrypt(row[6]) if row[6] else ""
                })
            except:
                continue
        return passwords
    
    def delete_password(self, pid):
        self.conn.execute("DELETE FROM passwords WHERE id=?", (pid,))
        self.conn.commit()
    
    def update_password(self, pid, site, login, password, category, comment):
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE passwords SET site=?, login=?, current_password=?, category=?, updated_at=?, comment=? WHERE id=?",
            (self.crypto.encrypt(site), self.crypto.encrypt(login), self.crypto.encrypt(password),
             category, now, self.crypto.encrypt(comment), pid)
        )
        self.conn.commit()
    
    def close(self):
        if self.conn:
            self.conn.close()

# ==================== ИНТЕРФЕЙС KIVY ====================
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=40, spacing=15)
        
        layout.add_widget(Label(text='🔒 SecurePass Keeper', font_size='32sp'))
        
        self.username = TextInput(hint_text='Логин', multiline=False, size_hint_y=0.12)
        self.password = TextInput(hint_text='Пароль', password=True, multiline=False, size_hint_y=0.12)
        
        layout.add_widget(self.username)
        layout.add_widget(self.password)
        
        btn_login = Button(text='Войти', background_color=(0.2, 0.6, 0.2, 1), size_hint_y=0.1)
        btn_login.bind(on_press=self.do_login)
        layout.add_widget(btn_login)
        
        btn_register = Button(text='Регистрация', size_hint_y=0.1)
        btn_register.bind(on_press=lambda x: setattr(self.manager, 'current', 'register'))
        layout.add_widget(btn_register)
        
        self.add_widget(layout)
    
    def do_login(self, instance):
        app = App.get_running_app()
        success, master_key = app.user_manager.login_user(self.username.text, self.password.text)
        
        if success and master_key:
            app.current_user = self.username.text
            app.master_key = master_key
            app.password_db = PasswordDatabase(app.current_user, master_key)
            self.manager.current = 'main'
            self.manager.get_screen('main').refresh_passwords()
        else:
            popup = Popup(title='Ошибка', content=Label(text='Неверный логин или пароль'), size_hint=(0.8, 0.3))
            popup.open()

class RegisterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=40, spacing=15)
        
        layout.add_widget(Label(text='📝 Регистрация', font_size='28sp'))
        
        self.username = TextInput(hint_text='Логин', multiline=False, size_hint_y=0.12)
        self.password = TextInput(hint_text='Пароль', password=True, multiline=False, size_hint_y=0.12)
        self.confirm = TextInput(hint_text='Подтвердите пароль', password=True, multiline=False, size_hint_y=0.12)
        
        layout.add_widget(self.username)
        layout.add_widget(self.password)
        layout.add_widget(self.confirm)
        
        btn_register = Button(text='Зарегистрироваться', background_color=(0.2, 0.6, 0.2, 1), size_hint_y=0.1)
        btn_register.bind(on_press=self.do_register)
        layout.add_widget(btn_register)
        
        btn_back = Button(text='Назад', size_hint_y=0.1)
        btn_back.bind(on_press=lambda x: setattr(self.manager, 'current', 'login'))
        layout.add_widget(btn_back)
        
        self.add_widget(layout)
    
    def do_register(self, instance):
        app = App.get_running_app()
        
        if self.password.text != self.confirm.text:
            popup = Popup(title='Ошибка', content=Label(text='Пароли не совпадают'), size_hint=(0.8, 0.3))
            popup.open()
            return
        
        if len(self.password.text) < 4:
            popup = Popup(title='Ошибка', content=Label(text='Пароль должен быть не менее 4 символов'), size_hint=(0.8, 0.3))
            popup.open()
            return
        
        if app.user_manager.register_user(self.username.text, self.password.text):
            popup = Popup(title='Успех', content=Label(text='Регистрация успешна!'), size_hint=(0.6, 0.2))
            popup.open()
            self.manager.current = 'login'
        else:
            popup = Popup(title='Ошибка', content=Label(text='Пользователь уже существует'), size_hint=(0.8, 0.3))
            popup.open()

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.passwords = []
        self.selected_index = None
        
        layout = BoxLayout(orientation='vertical', padding=10, spacing=5)
        
        # Верхняя панель
        top = BoxLayout(size_hint_y=0.1, spacing=5)
        self.search_input = TextInput(hint_text='Поиск...', multiline=False, size_hint_x=0.7)
        top.add_widget(self.search_input)
        
        btn_search = Button(text='🔍', size_hint_x=0.15)
        btn_search.bind(on_press=self.search)
        top.add_widget(btn_search)
        
        btn_add = Button(text='+', size_hint_x=0.15, background_color=(0.2, 0.6, 0.2, 1))
        btn_add.bind(on_press=self.add_password)
        top.add_widget(btn_add)
        layout.add_widget(top)
        
        # Список паролей (ScrollView)
        self.scroll = ScrollView()
        self.list_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.scroll.add_widget(self.list_layout)
        layout.add_widget(self.scroll)
        
        # Нижняя панель
        bottom = BoxLayout(size_hint_y=0.12, spacing=5)
        
        btn_copy_pass = Button(text='📋 Пароль')
        btn_copy_pass.bind(on_press=self.copy_password)
        bottom.add_widget(btn_copy_pass)
        
        btn_copy_login = Button(text='📋 Логин')
        btn_copy_login.bind(on_press=self.copy_login)
        bottom.add_widget(btn_copy_login)
        
        btn_edit = Button(text='✏️')
        btn_edit.bind(on_press=self.edit_password)
        bottom.add_widget(btn_edit)
        
        btn_delete = Button(text='🗑️')
        btn_delete.bind(on_press=self.delete_password)
        bottom.add_widget(btn_delete)
        
        layout.add_widget(bottom)
        
        self.add_widget(layout)
    
    def refresh_passwords(self):
        self.list_layout.clear_widgets()
        app = App.get_running_app()
        
        search_text = self.search_input.text.lower()
        all_passwords = app.password_db.get_all_passwords()
        
        self.passwords = [p for p in all_passwords 
                         if search_text in p['site'].lower() or search_text in p['login'].lower()]
        
        for i, p in enumerate(self.passwords):
            item = BoxLayout(size_hint_y=None, height=60, padding=5)
            
            info = BoxLayout(orientation='vertical', size_hint_x=0.7)
            info.add_widget(Label(text=p['site'], font_size='16sp', bold=True, size_hint_y=0.5))
            info.add_widget(Label(text=p['login'], font_size='12sp', size_hint_y=0.5))
            item.add_widget(info)
            
            select_btn = Button(text='Выбрать', size_hint_x=0.3, background_color=(0.4, 0.4, 0.4, 1))
            select_btn.bind(on_press=lambda x, idx=i: self.select_item(idx))
            item.add_widget(select_btn)
            
            self.list_layout.add_widget(item)
    
    def select_item(self, idx):
        self.selected_index = idx
        popup = Popup(title='Выбрано', content=Label(text=f'Выбрано: {self.passwords[idx]["site"]}'), size_hint=(0.6, 0.2))
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 1)
    
    def search(self, instance):
        self.refresh_passwords()
    
    def add_password(self, instance):
        self.show_password_popup()
    
    def edit_password(self, instance):
        if self.selected_index is not None:
            data = self.passwords[self.selected_index]
            self.show_password_popup(data)
        else:
            popup = Popup(title='Ошибка', content=Label(text='Сначала выберите запись'), size_hint=(0.8, 0.3))
            popup.open()
    
    def delete_password(self, instance):
        if self.selected_index is not None:
            app = App.get_running_app()
            data = self.passwords[self.selected_index]
            app.password_db.delete_password(data['id'])
            self.refresh_passwords()
            self.selected_index = None
        else:
            popup = Popup(title='Ошибка', content=Label(text='Сначала выберите запись'), size_hint=(0.8, 0.3))
            popup.open()
    
    def copy_password(self, instance):
        if self.selected_index is not None:
            data = self.passwords[self.selected_index]
            Clipboard.copy(data['password'])
            popup = Popup(title='Скопировано', content=Label(text='Пароль скопирован'), size_hint=(0.6, 0.2))
            popup.open()
            Clock.schedule_once(lambda dt: popup.dismiss(), 1.5)
        else:
            popup = Popup(title='Ошибка', content=Label(text='Сначала выберите запись'), size_hint=(0.8, 0.3))
            popup.open()
    
    def copy_login(self, instance):
        if self.selected_index is not None:
            data = self.passwords[self.selected_index]
            Clipboard.copy(data['login'])
            popup = Popup(title='Скопировано', content=Label(text='Логин скопирован'), size_hint=(0.6, 0.2))
            popup.open()
            Clock.schedule_once(lambda dt: popup.dismiss(), 1.5)
        else:
            popup = Popup(title='Ошибка', content=Label(text='Сначала выберите запись'), size_hint=(0.8, 0.3))
            popup.open()
    
    def show_password_popup(self, data=None):
        app = App.get_running_app()
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        site = TextInput(hint_text='Сайт', multiline=False)
        login = TextInput(hint_text='Логин', multiline=False)
        password = TextInput(hint_text='Пароль', multiline=False)
        category = TextInput(hint_text='Категория', multiline=False)
        
        if data:
            site.text = data['site']
            login.text = data['login']
            password.text = data['password']
            category.text = data.get('category', 'Сайты')
        
        content.add_widget(site)
        content.add_widget(login)
        content.add_widget(password)
        content.add_widget(category)
        
        def save(instance):
            if site.text and login.text and password.text:
                cat = category.text if category.text else 'Сайты'
                if data:
                    app.password_db.update_password(data['id'], site.text, login.text, password.text, cat, '')
                else:
                    app.password_db.add_password(site.text, login.text, password.text, cat, '')
                popup.dismiss()
                self.refresh_passwords()
            else:
                err = Popup(title='Ошибка', content=Label(text='Заполните сайт, логин и пароль'), size_hint=(0.8, 0.3))
                err.open()
        
        btns = BoxLayout(size_hint_y=0.15, spacing=5)
        save_btn = Button(text='Сохранить', background_color=(0.2, 0.6, 0.2, 1))
        save_btn.bind(on_press=save)
        cancel_btn = Button(text='Отмена')
        cancel_btn.bind(on_press=lambda x: popup.dismiss())
        btns.add_widget(save_btn)
        btns.add_widget(cancel_btn)
        content.add_widget(btns)
        
        title = 'Новая запись' if not data else 'Редактирование'
        popup = Popup(title=title, content=content, size_hint=(0.9, 0.7))
        popup.open()

class SecurePassApp(App):
    def build(self):
        self.user_manager = UserManager()
        self.current_user = None
        self.master_key = None
        self.password_db = None
        
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(RegisterScreen(name='register'))
        sm.add_widget(MainScreen(name='main'))
        return sm
    
    def on_stop(self):
        if self.password_db:
            self.password_db.close()
        if self.user_manager:
            self.user_manager.close()

if __name__ == '__main__':
    SecurePassApp().run()