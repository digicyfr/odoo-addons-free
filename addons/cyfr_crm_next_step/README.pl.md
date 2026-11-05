# Kolejka następnych działań CRM dla Odoo 19

Moduł pokazuje aktywne potencjalne szanse i leady, które nie mają zaplanowanego działania albo mają co najmniej jedno zaległe działanie. Korzysta z istniejących rekordów CRM i działań Odoo. Otwarcie kolejki nie zmienia danych.

## Instalacja

Zainstaluj folder modułu na serwerze Odoo 19. Jedyną zależnością jest standardowy moduł `crm`. Moduł działa samodzielnie, bez innych dodatków Cyfr. Przeznaczony jest dla Odoo Community i Enterprise na Odoo.sh lub własnym serwerze. Wersja Enterprise nie została jeszcze sprawdzona. Odoo Online nie obsługuje dowolnych dodatków serwerowych.

## Użycie

1. Jako sprzedawca lub kierownik otwórz **CRM → Sprzedaż → Kolejka następnych działań**.
2. Kolumna **Stan następnego działania** podaje powód pojawienia się rekordu. Przełącz filtr **Brak zaplanowanego działania** lub **Zaległe działanie**. Szukaj i grupuj według sprzedawcy, zespołu i firmy.
3. Otwórz lead i użyj standardowego planowania działań Odoo. Lista pokazuje aktualny stan działań bez osobnego zadania cyklicznego.

Działanie z terminem na dziś nie jest zaległe. Jeśli istnieje działanie zaległe, lead pozostaje w kolejce również wtedy, gdy ma inne działanie na przyszłość. Działanie zakończone nie liczy się jako zaplanowane. Odoo oblicza termin według strefy czasowej osoby przypisanej do działania. Wygrane, utracone i zarchiwizowane rekordy nie pojawiają się w kolejce.

## Zakres i bezpieczeństwo

Moduł nie wysyła wiadomości, nie tworzy automatycznie działań i nie szacuje daty ostatniego kontaktu z klientem. Nie ma dodatkowego modelu ani kopii danych leadów. Obowiązują standardowe uprawnienia CRM i reguły dostępu do firm. Dane demonstracyjne są fikcyjne i instalowane tylko w trybie demo. Szczegóły: [SECURITY.md](SECURITY.md). Licencja: [LGPL-3](LICENSE).
