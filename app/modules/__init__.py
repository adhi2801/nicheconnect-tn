"""The modules of the one app, in layers (D-099; docs/standards/backend.md section 1).

A module imports only from layers below it; `lint-imports` fails CI otherwise.

    7  me          (the export reads every table, admin's reports too)
    6  admin
    5  matching | insights | passport
    4  campaigns : deal_memo : payment_status : disputes
    3  profiles | safety | notifications
    2  auth

`|` keeps siblings apart; `:` lets the deal domain import across itself until
phase 2 untangles it. `app.core` and `app.db` sit below every module and
never import one.
"""
