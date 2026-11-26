from .payment_api import PaymentCreateAPIView, RefundCreateAPIView
from .invoice_actions_api import InvoiceItemCreateAPIView, InvoiceIssueAPIView, InvoiceVoidAPIView
from .invoice_api import InvoiceListAPIView
from .category_api import IncomeCategoryListAPIView, ExpenseCategoryListAPIView
from django.urls import path

from .api_views import AccountListAPIView

urlpatterns = [
    path("refunds/", RefundCreateAPIView.as_view(), name="accounting-refunds"),
    path("payments/", PaymentCreateAPIView.as_view(), name="accounting-payments"),
    path("invoices/<uuid:invoice_id>/void/", InvoiceVoidAPIView.as_view(), name="accounting-invoice-void"),
    path("invoices/<uuid:invoice_id>/issue/", InvoiceIssueAPIView.as_view(), name="accounting-invoice-issue"),
    path("invoices/<uuid:invoice_id>/items/", InvoiceItemCreateAPIView.as_view(), name="accounting-invoice-add-item"),
    path("invoices/", InvoiceListAPIView.as_view(), name="accounting-invoices"),
    path("expense-categories/", ExpenseCategoryListAPIView.as_view(), name="accounting-expense-categories"),
    path("income-categories/", IncomeCategoryListAPIView.as_view(), name="accounting-income-categories"),
    path("accounts/", AccountListAPIView.as_view(), name="accounting-accounts"),
]


# EXPENSE MANAGEMENT API
from .expense_api import (
    ExpenseCreateAPIView,
    ExpenseActionAPIView,
)

urlpatterns += [
    path(
        "expenses/",
        ExpenseCreateAPIView.as_view(),
        name="accounting-expense-create",
    ),
] + [
    path(
        f"expenses/<uuid:expense_id>/{action}/",
        ExpenseActionAPIView.as_view(action=action),
        name=f"accounting-expense-{action}",
    )
    for action in (
        "submit",
        "approve",
        "reject",
        "pay",
        "reverse",
    )
]


# EXPENSE DETAIL API
from .expense_api import ExpenseDetailAPIView

urlpatterns += [
    path(
        "expenses/<uuid:expense_id>/",
        ExpenseDetailAPIView.as_view(),
        name="accounting-expense-detail",
    ),
]


# TRANSACTION LEDGER API

from .transaction_api import (
    TransactionListAPIView,
    TransactionDetailAPIView,
)

urlpatterns += [
    path(
        "transactions/",
        TransactionListAPIView.as_view(),
        name="accounting-transactions",
    ),
    path(
        "transactions/<uuid:transaction_id>/",
        TransactionDetailAPIView.as_view(),
        name="accounting-transaction-detail",
    ),
]


# ACCOUNT BALANCE API

from .balance_api import (
    AccountBalanceListAPIView,
    AccountBalanceDetailAPIView,
)

urlpatterns += [
    path(
        "accounts/balances/",
        AccountBalanceListAPIView.as_view(),
        name="accounting-account-balances",
    ),
    path(
        "accounts/<uuid:account_id>/balance/",
        AccountBalanceDetailAPIView.as_view(),
        name="accounting-account-balance-detail",
    ),
]


# FINANCIAL REPORTING API

from .report_api import FinancialSummaryAPIView

urlpatterns += [
    path(
        "reports/financial-summary/",
        FinancialSummaryAPIView.as_view(),
        name="accounting-financial-summary",
    ),
]
