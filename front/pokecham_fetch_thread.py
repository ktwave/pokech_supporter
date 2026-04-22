from PySide6.QtCore import QThread, Signal

from backend.logic.pokecham_scraper import scrape_pokemon_page


class PokechamFetchThread(QThread):
    finished_ok = Signal(str, dict, int)
    finished_err = Signal(str, str, int)

    def __init__(self, japanese_name: str, url: str, generation: int):
        super().__init__()
        self._japanese_name = japanese_name
        self._url = url
        self._generation = generation

    def run(self):
        try:
            data = scrape_pokemon_page(self._url)
            self.finished_ok.emit(self._japanese_name, data, self._generation)
        except Exception as e:
            self.finished_err.emit(self._japanese_name, str(e), self._generation)
