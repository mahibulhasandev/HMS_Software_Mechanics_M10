from .category_api import IncomeCategoryListAPIView, ExpenseCategoryListAPIView
from django.urls import path

from .api_views import AccountListAPIView

urlpatterns = [
    path("expense-categories/", ExpenseCategoryListAPIView.as_view(), name="accounting-expense-categories"),
    path("income-categories/", IncomeCategoryListAPIView.as_view(), name="accounting-income-categories"),
    path("accounts/", AccountListAPIView.as_view(), name="accounting-accounts"),
]
