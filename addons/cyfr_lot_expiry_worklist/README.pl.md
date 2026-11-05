# Lista terminów ważności partii dla Odoo 19

Ten moduł LGPL-3 dodaje listę zadań dla zapasów z terminem ważności do standardowego `product_expiry`. Nie zastępuje alertów Odoo ani nie zmienia stanów magazynowych.

## Instalacja i użycie

Zainstaluj **Lot Expiry Worklist**. Odoo doinstaluje `product_expiry` i `stock`. Nadaj użytkownikom standardowe role Użytkownik magazynu lub Administrator magazynu. W **Magazyn → Terminy ważności partii → Skanuj** administrator wybiera lokalizację wewnętrzną należącą do firmy oraz horyzont 0–365 dni. Skan obejmuje aktywne podlokalizacje wewnętrzne, ale każda dokładna lokalizacja ma osobny wiersz. W **Magazyn → Terminy ważności partii → Lista zadań** widać ostatnie migawki i zadania zachowane po usunięciu zapasu z lokalizacji.

Administrator przypisuje odpowiedzialnego użytkownika magazynu, następny krok i notatkę dla każdej kombinacji firmy, partii, dokładnej lokalizacji i właściciela. Osoba przypisana albo administrator potwierdza zadanie. Ponowne przypisanie zeruje potwierdzenie. Zmiany przypisania są zapisane w historii wiadomości. Przyciski **Otwórz partię w Odoo** i **Bieżące kwanty** otwierają standardowe widoki Odoo. Po zmianie ruchów, rezerwacji, dat partii lub właściciela uruchom skan ponownie.

## Znaczenie ilości i dat

Wiersz sumuje kwanty z różnych paczek dla **firmy × partii × dokładnej lokalizacji wewnętrznej × właściciela zapasu**. Zapas bez zewnętrznego właściciela jest oddzielony od zapasu konsygnacyjnego. Nowy wiersz wymaga dodatniej ilości netto. Ilości zerowe lub ujemne, lokalizacje klienta/dostawcy/tranzytowe, nieaktywne i bez firmy oraz produkty bez śledzenia dat ważności nie tworzą aktywnych wierszy. Po spadku ilości do zera wcześniejszy wiersz pozostaje w historii z oznaczeniem braku zapasu.

**Fizycznie niezarezerwowana** ilość to stan na ręku minus ilość zarezerwowana, w podstawowej jednostce produktu, w chwili skanu. To nie jest natywne `available_quantity`, które Odoo może wyzerować po dacie usunięcia. Skan porównuje wyłącznie zapisaną `expiration_date` partii z bieżącą chwilą UTC plus wybraną liczbą pełnych okresów 24-godzinnych. `alert_date`, `use_date` i `removal_date` są wyświetlane osobno. Stan „Expired” oznacza `expiration_date <= teraz`; „Within Horizon” oznacza przyszłą datę w horyzoncie. Dane są migawką i starzeją się do następnego skanu.

Jeden skan odczytuje najwyżej 5000 kwantów partii i 1000 pozycji partii, łącznie z wcześniejszymi zadaniami, w wybranej lokalizacji. Okno skanowania pokazuje oba limity. Po przekroczeniu któregokolwiek limitu kończy się bez częściowej aktualizacji; wybierz węższą lokalizację. Nie ma harmonogramu automatycznego skanowania.

Moduł nie przenosi, rezerwuje ani likwiduje zapasów, nie zmienia dat partii ani księgowań i nie udziela porad dotyczących ustawowych terminów przydatności. Standardowe alerty Odoo działają nadal. Odoo Online nie obsługuje niestandardowych modułów serwerowych. Enterprise nie było dostępne do weryfikacji; sprawdzono środowisko Community instalowane samodzielnie.
