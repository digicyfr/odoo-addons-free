# Lista ofert wymagających działania — Odoo 19

Ręczna lista ofert, których termin ważności się zbliża lub które nie mają **przyszłej** aktywności. Moduł nie zmienia ofert i nie wysyła wiadomości klientom.

## Użycie

1. Otwórz **Sprzedaż → Zamówienia → Lista ofert**. Menedżer sprzedaży ustawia horyzont 0–90 dni w **Sprzedaż → Konfiguracja → Horyzont listy ofert**; domyślnie jest to siedem dni.
2. Wybierz firmę, sprzedawcę, zespół lub zakres dat ważności i uruchom skan. Jedno skanowanie sprawdza maksymalnie 2000 najnowszych ofert w stanie szkic/wysłana i pokazuje najwyżej 500 wyników. Po osiągnięciu limitu formularz pozostaje otwarty i pokazuje ostrzeżenie oraz liczniki. Otwórz częściowe wyniki przez **Pokaż ostatni skan** albo zawęź filtry i uruchom skan ponownie.
3. Otwórz natywny formularz oferty albo okno planowania aktywności. Aktywność powstaje dopiero po zapisaniu tego okna.

Aktywność z terminem jutro lub później jest przyszła. Termin dzisiejszy lub przeterminowany nie jest przyszły i ma osobny znacznik. Brak daty ważności jest osobnym powodem, a nie „przeterminowaniem”. Filtr dat pomija oferty bez daty ważności. Oferta przeterminowana lub bliska końca pozostaje na liście nawet wtedy, gdy ma przyszłą aktywność.

Wyniki są tymczasową migawką dostępną tylko autorowi skanu. Każdy odczyt i eksport ponownie respektuje bieżące uprawnienia do oferty w Odoo. Skanowanie nie wysyła e-maili, nie anuluje ofert i nie tworzy aktywności.

## Instalacja i ograniczenia

Zainstaluj `cyfr_quote_watchlist` w Odoo 19. Zależność `sale_management` udostępnia menu Sprzedaży. Skan jest ograniczony do 2000 kandydatów i 500 wyników; duże bazy wymagają zawężenia filtrów. Dzień odniesienia to lokalny dzień użytkownika. Ukrytych aktywności nie można wywnioskować. Odoo 19 Community jest objęte weryfikacją; Enterprise pozostaje nieweryfikowane.

Licencja: LGPL-3. Patrz [LICENSE](LICENSE).
