# Dowody zwrotów POS (Odoo 19)

Bezpłatna kolejka dowodów dla zwrotów obsługiwanych przez standardowy moduł POS Odoo. Po zapisaniu natywnego zwrotu lub synchronizacji POS dodatek tworzy jedną sprawę dla każdego zamówienia z flagą zwrotu. Użytkownik Odoo przypisany do zamówienia lub kierownik POS może wybrać powód i wpisać opis stanu towaru. Kierownik przegląda niekompletne sprawy oraz grupuje je według powodu, punktu sprzedaży, daty i firmy. Każda pozycja zwrotu pokazuje powiązaną pozycję i zamówienie pierwotnej sprzedaży, jeżeli Odoo udostępnia to powiązanie.

## Instalacja i użycie

Zainstaluj `cyfr_pos_refund_evidence` w Odoo 19 z modułem Punkt sprzedaży. Kierownik dodaje powody w **Punkt sprzedaży → Konfiguracja → Powody zwrotów**. Po wykonaniu zwykłego zwrotu otwórz **Punkt sprzedaży → Zamówienia → Dowody zwrotów** i uzupełnij sprawę. Użytkownik POS widzi sprawy zamówień, których standardowe pole `user_id` wskazuje jego konto Odoo; konto może być współdzielone przez kasjerów. Kierownik widzi sprawy firm, do których ma dostęp. Pole „Zapisane przez” wskazuje osobę, która ostatnio zmieniła powód lub opis; nie oznacza automatycznie osoby otwierającej sesję POS.

Domyślnie włączony jest filtr „Niekompletne”. Usuń filtr, aby zobaczyć pozostałe sprawy. Jeżeli liczba pierwotnych zamówień wynosi zero, pozycje zwrotu nie mają natywnego powiązania ze sprzedażą. Takiej sprzedaży dodatek nie zgaduje. Standardowy interfejs POS synchronizuje zwrot z jednego zamówienia pierwotnego; model serwera potrafi przedstawić wiele zamówień i dodatek pokazuje wszystkie powiązania.

## Zakres i dane

Dodatek obejmuje wyłącznie zamówienia z `is_refund=True`. Nie obejmuje ręcznych ujemnych pozycji bez tej flagi. Nie zmienia płatności, podatków, magazynu, faktur ani księgowania. Nie dodaje okna kasjera, trybu offline ani załączników. Sprawa powstaje po zapisaniu natywnego zwrotu i nie blokuje zwrotu.

Sprawy odwołują się do natywnych zamówień i pozycji; nie kopiują danych klienta do osobnej tabeli. W opisie stanu nie należy wpisywać danych osobowych. Usunięcie zamówienia zwrotu usuwa powiązaną sprawę. Powody można archiwizować; powodu użytego w sprawie nie można usunąć. Stosuj firmowe zasady retencji i kopii zapasowych dla POS.

Jest to kolejka przeglądu operacyjnego, a nie rejestr odporny na zmiany. Uprawnieni użytkownicy POS mogą poprawić dowody, a standardowe uprawnienia mogą pozwalać na usunięcie zamówienia wraz ze sprawą.

Dane demonstracyjne zawierają trzy powody dla głównej firmy. Testy tworzą syntetyczne zwroty pełne, częściowe i z wieloma źródłami. Trwałych demonstracyjnych sesji, zamówień ani drugiej firmy nie instalujemy, aby odinstalowanie było czyste. Zależność: `point_of_sale`; licencja LGPL-3; wersja `19.0.1.0.0`.
