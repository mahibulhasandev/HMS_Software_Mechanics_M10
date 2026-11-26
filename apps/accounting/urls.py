from .invoice_actions_api import InvoiceItemCreateAPIView, InvoiceIssueAPIView, InvoiceVoidAPIView
from .invoice_api import InvoiceListAPIView
from .category_api import IncomeCategoryListAPIView, ExpenseCategoryListAPIView
from django.urls import path

from .api_views import AccountListAPIView

urlpatterns = [
    path("invoices/<uuid:invoice_id>/void/", InvoiceVoidAPIView.as_view(), name="accounting-invoice-void"),
    path("invoices/<uuid:invoice_id>/issue/", InvoiceIssueAPIView.as_view(), name="accounting-invoice-issue"),
    path("invoices/<uuid:invoice_id>/items/", InvoiceItemCreateAPIView.as_view(), name="accounting-invoice-add-item"),
    path("invoices/", InvoiceListAPIView.as_view(), name="accounting-invoices"),
    path("expense-categories/", ExpenseCategoryListAPIView.as_view(), name="accounting-expense-categories"),
    path("income-categories/", IncomeCategoryListAPIView.as_view(), name="accounting-income-categories"),
    path("accounts/", AccountListAPIView.as_view(), name="accounting-accounts"),
]
