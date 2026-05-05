import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

class KinApp(toga.App):
    def startup(self):
        main_box = toga.Box(style=Pack(direction=COLUMN))
        
        self.label = toga.Label(
            'Kin is online.',
            style=Pack(padding=20, font_size=16)
        )
        
        self.input = toga.TextInput(
            placeholder='Say something...',
            style=Pack(flex=1, padding=5)
        )
        
        btn = toga.Button(
            'Send',
            on_press=self.send,
            style=Pack(padding=5)
        )
        
        input_row = toga.Box(
            children=[self.input, btn],
            style=Pack(direction=ROW, padding=5)
        )
        
        main_box.add(self.label)
        main_box.add(input_row)
        
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

    def send(self, widget):
        text = self.input.value
        if text:
            self.label.text = f'You said: {text}'
            self.input.value = ''

def main():
    return KinApp('Kin', 'org.savant.kin')
