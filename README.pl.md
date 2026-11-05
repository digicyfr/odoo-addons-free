# Bezpłatne moduły Digicyfr dla Odoo 19

To publiczne repozytorium zawiera oryginalne, niezależnie instalowane moduły
Odoo 19 na licencji LGPL-3. Każdy moduł ma własną dokumentację po angielsku i
polsku, dane demonstracyjne oraz testy.

| Moduł | Zastosowanie | Wymagana aplikacja Odoo |
| --- | --- | --- |
| [`cyfr_product_data_health`](addons/cyfr_product_data_health/README.pl.md) | Przegląd brakujących identyfikatorów, cen, kategorii i obrazów produktów po imporcie katalogu | `product` |
| [`cyfr_crm_next_step`](addons/cyfr_crm_next_step/README.pl.md) | Lista otwartych szans bez zaplanowanego działania lub z zaległym działaniem | `crm` |

## Instalacja

Użyj serwera Odoo 19 z możliwością instalowania własnych modułów albo Odoo.sh.
Umieść katalog modułu na ścieżce dodatków, odśwież listę aplikacji i zainstaluj
wybrany moduł. Archiwum ZIP przypisane do wydania zawiera jeden moduł.
Przed instalacją sprawdź sumę SHA-256 z dołączonego pliku.

Odoo Online nie pozwala instalować dowolnych modułów serwerowych. Wersja Odoo 19
Community została przetestowana zgodnie z informacjami w wydaniu; zgodność z
Enterprise nie została jeszcze sprawdzona.

Problemy zgłaszaj przez [GitHub Issues](https://github.com/digicyfr/odoo-addons-free/issues).
Nie publikuj haseł, ciasteczek sesji, prywatnych danych produktów ani eksportów
bazy danych. Zasady bezpieczeństwa opisano w `SECURITY.md` każdego modułu.

Kod, dokumentacja, tłumaczenia i ikona zostały przygotowane dla tego projektu.
Odoo jest znakiem towarowym Odoo S.A.; repozytorium nie jest oficjalnym
projektem Odoo.

Licencja: LGPL-3; zobacz [LICENSE](LICENSE).
