# Audyt konfiguracji podatków POS dla Odoo 19

Bezpłatny, wyłącznie odczytowy przegląd podatków dla kierownika Punktu Sprzedaży. Raport pokazuje podatki sprzedażowe produktów dostępnych w POS oraz wynik mapowania dla skonfigurowanych pozycji fiskalnych. Flagi są **informacyjne**: brak podatku lub kilka podatków może być zamierzone. Prawidłową stawkę należy ustalić z księgowym albo osobą odpowiedzialną za lokalizację.

## Instalacja i użycie

Zainstaluj katalog `cyfr_pos_tax_audit` jako dodatek Odoo 19. Jedyną zadeklarowaną zależnością jest `point_of_sale`. Otwórz **Punkt Sprzedaży → Konfiguracja → Audyt podatków**, utwórz skan dla wybranego POS i ustaw wielkość strony (1–100). Kliknij **Skanuj stronę**. Przejrzyj macierz, przejdź do następnej strony albo wyeksportuj CSV bieżącej strony. Otwórz wiersz macierzy, aby przejść do produktu lub pozycji fiskalnej; przyciski **Otwórz podatki źródłowe** i **Otwórz podatki wynikowe** prowadzą do formularza podatku albo przefiltrowanej listy. Menu **Macierz podatków** pozwala wyszukać wiersze tymczasowych skanów. Dostęp ma kierownik POS.

Skan używa standardowej domeny produktów POS Odoo 19: firma, aktywność, możliwość sprzedaży, dostępność w POS i ograniczenie kategorii. Obejmuje warianty pasujących produktów w kolejności identyfikatorów. POS może dodatkowo załadować produkt specjalny lub napiwek, element zestawu, produkt opcjonalny albo produkt obecny w zamówieniu; te przypadki kontekstowe są poza tym raportem. Początkowy, ograniczony zbiór POS może mieć inną kolejność. Pozycje fiskalne klienta lub ustawienia restauracyjne nie należą do tej macierzy. Strona ma limit 1000 wierszy, 2000 różnych podatków źródłowych lub wynikowych oraz 19 skonfigurowanych pozycji fiskalnych i scenariusz bazowy. Jeśli limit zostanie przekroczony, zmniejsz stronę lub liczbę skonfigurowanych pozycji.

„Brak podatku firmy” oznacza pusty zestaw podatków dla firmy POS. „Wiele podatków” jest opisem, a nie błędem. „Wyłączony podatek innej firmy” nie ujawnia nazwy obcego podatku. „Pusty wynik mapowania” może być poprawnym zwolnieniem. CSV zabezpiecza tekst przed wykonaniem formuł w arkuszu kalkulacyjnym.

Dane demonstracyjne zawierają produkt z podatkiem i bez podatku, ograniczoną kategorię POS oraz dwa scenariusze pozycji fiskalnych. Izolację między firmami sprawdzają tymczasowe rekordy testowe; dodatek nie tworzy demonstracyjnej firmy, dzięki czemu odinstalowanie usuwa jego dane demonstracyjne.

Skan i jego wiersze są tymczasowe. Dodatek nie zmienia produktów, podatków, pozycji fiskalnych, zamówień ani paragonów. Po odinstalowaniu dane handlowe pozostają bez zmian. Wersja `19.0.1.0.0` jest przeznaczona dla Odoo 19 Community na Odoo.sh lub własnym serwerze; Enterprise wymaga osobnego testu.
