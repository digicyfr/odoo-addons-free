# Kontrola danych produktów w Odoo 19

Moduł pokazuje braki w danych aktywnych wariantów produktów przeznaczonych do sprzedaży. Wyniki mają charakter informacyjny. Moduł nie zmienia produktów, cen ani podatków.

## Instalacja i konfiguracja

Zainstaluj `cyfr_product_data_health` w Odoo 19. Jedyną zależnością jest `product`. Menedżer produktów może zmienić reguły w **Data Health → Policies**. Dostępne kontrole: indeks, kod kreskowy, cena sprzedaży nie większa od zera, brakująca lub ogólna kategoria oraz brak zdjęcia. Każdą kontrolę można wyłączyć. Cena zero może być prawidłowa.

Pierwszeństwo reguł: firma i kategoria; firma; kategoria globalna; reguła globalna. Dla jednego zakresu może być aktywna tylko jedna reguła. Kategorie uznawane za ogólne należy wybrać jawnie.

## Skanowanie

1. Użytkownik z uprawnieniami menedżera produktów otwiera **Data Health → Scans**, tworzy skan i wybiera dostępną firmę.
2. Naciska **Scan next 200 products** aż status zmieni się na **Complete**. Każde naciśnięcie przetwarza maksymalnie 200 wariantów.
3. Otwiera **Current Issues** lub **View issues**. Przycisk **Open Product** otwiera standardowy formularz produktu. Standardowy eksport Odoo pozwala pobrać widoczne wiersze do CSV.

Nowy ukończony skan zastępuje poprzedni bieżący skan tej firmy. Nieukończony skan nie ukrywa poprzednich wyników. Stare skany można usunąć ręcznie.

## Zakres

Indeks i kod kreskowy są sprawdzane na wariancie, a cena i kategoria na szablonie. Zdjęcie wariantu może być odziedziczone z szablonu. Skan obejmuje wyłącznie aktywne produkty do sprzedaży, dostępne w wybranej firmie lub współdzielone. Moduł nie ocenia poprawności prawnej, stawek VAT, cenników ani marży.
