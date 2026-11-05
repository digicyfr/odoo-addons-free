# Lista opóźnionych przyjęć zakupowych

Bezpłatny, niezależny dodatek do Odoo 19 dla kupców monitorujących otwarte przyjęcia do magazynu. Licencja: LGPL-3. Jedyna zależność: `purchase_stock`.

## Użycie

1. Zainstaluj dodatek **Purchase Late Receipt Worklist** w bazie Odoo 19 z aplikacjami Zakupy i Magazyn.
2. Jako użytkownik Zakupów otwórz **Zakupy → Zamówienia → Opóźnione przyjęcia**.
3. Ustaw horyzont „Wkrótce” (0–90 dni) i opcjonalnie dostawcę, kupca, firmę albo zakres dat. Kliknij **Skanuj otwarte przyjęcia**.
4. Sprawdź opóźnione i zbliżające się pozycje, pozostałą ilość, dostawcę, kupca, zamówienie i powiązane przyjęcia. **Zaplanuj działanie** otwiera standardowy formularz działania Odoo dla zamówienia, z uzupełnioną informacją o pozycji. Zapisanie działania jest oddzielną czynnością użytkownika.

Wynik skanowania jest migawką. Po zmianie przyjęć lub zamówień uruchom skanowanie ponownie. Zmiana filtrów usuwa poprzednią migawkę. Listę wyników można filtrować po statusie, dostawcy, kupcu, firmie i dniu oczekiwania. Jeśli po skanie zmieni się termin dostawy, z dawnej pozycji nadal można otworzyć formularz działania: kupiec może chcieć wyjaśnić zmianę. Przed otwarciem formularza dodatek ponownie sprawdza potwierdzenie zamówienia, otwartą ilość i uprawnienia; aktualny status terminu uzyskasz przez ponowne skanowanie.

## Zakres

Lista obejmuje potwierdzone (`purchase`) pozycje zamówień na produkty fizyczne (`consu`) dostarczane do magazynu. Pomija zapytania ofertowe, anulowane zamówienia, sekcje, notatki, zaliczki, pozycje w pełni przyjęte lub przyjęte z nadwyżką, usługi i bezpośrednie dostawy do klienta. Jest to **lista przyjęć magazynowych**, nie wszystkich zobowiązań zakupowych.

Pozostała ilość to ilość zamówiona minus natywne `qty_received` pozycji, porównana z dokładnością jednostki miary tej pozycji. Standardowe reguły Odoo dla ruchów magazynowych uwzględniają kwalifikujące się zwroty. Status korzysta ze strefy czasowej użytkownika i lokalnego dnia: wcześniejszy niż dziś to **Opóźnione**, dziś do końca horyzontu to **Wkrótce**. **Brak daty** dotyczy wyjątkowych danych migrowanych; standardowy Odoo 19 wymaga daty dla zwykłej pozycji.

Skan sprawdza najwyżej 2000 kandydatów i pokazuje najwyżej 500 otwartych pozycji. Po osiągnięciu limitu pojawia się ostrzeżenie; zawęź filtry i skanuj ponownie. Dodatek nie prognozuje nowego ETA ani nie zmienia terminów dostawcy, dat, ruchów, przyjęć, zamówień lub księgowań.

## Bezpieczeństwo i zgodność

Użytkownik Zakupów widzi tylko firmy dostępne w jego sesji. Migawka należy do jej autora. Dostęp do źródłowej pozycji i zamówienia jest ponownie sprawdzany przed otwarciem powiązań lub formularza działania. Standardowy formularz Odoo stosuje swoje uprawnienia przy zapisie.

Kod sprawdzono względem Odoo Server **19.0-20260908** (`odoo@sha256:a627eda6b4154eead21c4fca55f84f1671d870ca111aa57f93ca305861bc4613`). Wyniki testów i ograniczenia są opisane w `CHANGELOG.md`, `SECURITY.md` oraz specyfikacji modułu. Testy Enterprise wymagają oddzielnego potwierdzenia.
