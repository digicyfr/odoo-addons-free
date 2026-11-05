# Bezpłatne moduły Digicyfr dla Odoo 19

To publiczne repozytorium zawiera oryginalne, niezależnie instalowane moduły
Odoo 19 na licencji LGPL-3. Każdy moduł ma własną dokumentację po angielsku i
polsku, dane demonstracyjne oraz testy.

| Moduł | Zastosowanie | Wymagana aplikacja Odoo |
| --- | --- | --- |
| [`cyfr_product_data_health`](addons/cyfr_product_data_health/README.pl.md) | Przegląd brakujących identyfikatorów, cen, kategorii i obrazów produktów po imporcie katalogu | `product` |
| [`cyfr_crm_next_step`](addons/cyfr_crm_next_step/README.pl.md) | Lista otwartych szans bez zaplanowanego działania lub z zaległym działaniem | `crm` |
| [`cyfr_pos_tax_audit`](addons/cyfr_pos_tax_audit/README.pl.md) | Przegląd podatków katalogu POS i mapowań skonfigurowanych pozycji fiskalnych przed rozpoczęciem sprzedaży | `point_of_sale` |
| [`cyfr_stock_exception_queue`](addons/cyfr_stock_exception_queue/README.pl.md) | Przegląd ujemnych i niedostępnych stanów magazynowych w kolejce informacyjnej | `stock` |
| [`cyfr_purchase_receipt_delays`](addons/cyfr_purchase_receipt_delays/README.pl.md) | Lista opóźnionych i zbliżających się przyjęć zakupowych z działaniami następnymi | `purchase_stock` |
| [`cyfr_website_language_audit`](addons/cyfr_website_language_audit/README.pl.md) | Przegląd tłumaczeń stron oraz lokalizowanych danych SEO i opisów obrazów | `website` |
| [`cyfr_quote_watchlist`](addons/cyfr_quote_watchlist/README.pl.md) | Lista ofert według terminu ważności i brakujących przyszłych działań | `sale_management` |
| [`cyfr_pos_refund_evidence`](addons/cyfr_pos_refund_evidence/README.pl.md) | Rejestrowanie powodów zwrotów i powiązania z pierwotną sprzedażą po natywnym zwrocie POS | `point_of_sale` |
| [`cyfr_lot_expiry_worklist`](addons/cyfr_lot_expiry_worklist/README.pl.md) | Przypisywanie i potwierdzanie działań dla partii według lokalizacji i właściciela zapasu | `product_expiry` |
| [`cyfr_pos_shift_handover`](addons/cyfr_pos_shift_handover/README.pl.md) | Przekazywanie zadań operacyjnych między sesjami tego samego punktu sprzedaży | `point_of_sale` |

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
