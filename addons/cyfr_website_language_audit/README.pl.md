# Audyt językowy witryny dla Odoo 19

Moduł pomaga przejrzeć opublikowane strony jednej witryny w włączonym języku innym niż domyślny. Wskazuje statyczny tekst identyczny z wersją źródłową, brak jawnego tłumaczenia tytułu lub opisu SEO oraz obrazy bez opisu `alt`. Wyniki są wskazówkami do sprawdzenia. Identyczny tekst może być zamierzony, a pusty tytuł SEO może oznaczać użycie domyślnego tytułu Odoo.

## Instalacja i użycie

Zainstaluj aplikację `website`, a następnie ten moduł. Włącz język docelowy w ustawieniach witryny. Projektant witryny otwiera **Witryna → Raportowanie → Audyty językowe**, tworzy audyt dla witryny i języka, opcjonalnie podaje nazwy marek pomijane przy dokładnym dopasowaniu i uruchamia skan. Edytor z ograniczonymi uprawnieniami może czytać wyniki. Projektant może otworzyć stronę w natywnym edytorze Odoo, przełączyć język, poprawić treść i utworzyć nowy audyt.

Skan obejmuje strony przypisane do wybranej witryny oraz strony wspólne bez aktywnego lokalnego odpowiednika z adresem URL. Pomija strony nieopublikowane, nieaktywne, zabezpieczone hasłem, ograniczone do grup i zaplanowane na przyszłość. Aktywny, nieopublikowany lokalny odpowiednik wyklucza stronę wspólną w tej witrynie. Jeśli taki odpowiednik pojawi się po skanie, wcześniejsze wyniki dotyczące strony wspólnej zostaną ukryte. Odoo 19 nie ma osobnego stanu publikacji strony dla każdego języka.

## Zakres i ograniczenia

- Maksymalnie 600 lokalnych i 600 wspólnych kandydatów, 200 stron, 256 KiB i 2500 węzłów XML na stronę, 2000 wyników oraz 30 sekund przetwarzania. Przekroczenie limitu daje stan **Ucięty**. Niebezpieczny lub błędny XML daje stan **Niepowodzenie** i licznik błędów; część wyników może być niepełna.
- Porównanie dotyczy tylko statycznych węzłów o tej samej ścieżce XML, także wewnątrz standardowego szablonu strony `website.layout`. Inne wywołania szablonów, dynamiczne wyrażenia QWeb, warunkowe fragmenty, skrypty i zmieniona struktura są pomijane. Moduł nie renderuje strony, nie uruchamia JavaScriptu ani nie jest pełnym audytem dostępności.
- `alt=""`, `role="presentation"` i `aria-hidden="true"` oznaczają dekoracyjny obraz. Brak `alt`, sam biały znak lub ogólny opis taki jak „image” są wskazywane. Tekst krótszy niż 12 znaków jest pomijany, podobnie jak dokładnie dopasowane nazwy podane przez użytkownika.
- Brak tłumaczenia SEO jest sprawdzany w zapisanych tłumaczeniach Odoo, ponieważ zwykły odczyt może pokazywać wartość zastępczą w języku angielskim.

Audyt zapisuje tylko metadane, adres strony, ścieżkę węzła i skrót SHA-256 tekstu źródłowego lub ścieżki węzła. Nie kopiuje treści stron ani tłumaczeń. Projektant może usunąć stare audyty wraz z wynikami. Moduł nie wysyła danych na zewnątrz i nie tłumaczy automatycznie. Licencja: LGPL-3.
