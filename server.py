from fastmcp import FastMCP
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import json
import logging
import os


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_PATH = os.path.join(BASE_DIR, "categories.json")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("trackmyexpense")


# ============================================================
# MCP SERVER
# ============================================================

mcp = FastMCP("TrackMyExpense")


# ============================================================
# DATABASE
# ============================================================

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    },
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    """
    Initialize all application tables.
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:

            # ------------------------------------------------
            # Expenses
            # ------------------------------------------------

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL
                        CHECK (amount > 0),
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP NULL
                )
                """
            )

            # ------------------------------------------------
            # Budgets
            # ------------------------------------------------

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS budgets (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL,
                    month DATE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL
                        CHECK (amount > 0),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category, month)
                )
                """
            )

            # ------------------------------------------------
            # Indexes
            # ------------------------------------------------

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_expenses_date
                ON expenses(date)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_expenses_category
                ON expenses(category)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_expenses_deleted_at
                ON expenses(deleted_at)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_budgets_month
                ON budgets(month)
                """
            )

    logger.info("Database initialized successfully")


# ============================================================
# VALIDATION HELPERS
# ============================================================

def validate_date(value: str, field_name: str = "date") -> date:
    """
    Validate and convert YYYY-MM-DD string into date.
    """

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"{field_name} must be in YYYY-MM-DD format"
        )


def validate_date_range(start_date: str, end_date: str):
    """
    Validate a date range.
    """

    start = validate_date(start_date, "start_date")
    end = validate_date(end_date, "end_date")

    if start > end:
        raise ValueError(
            "start_date cannot be after end_date"
        )

    return start, end


def validate_amount(amount: float):
    """
    Validate monetary amount.
    """

    if amount <= 0:
        raise ValueError(
            "amount must be greater than 0"
        )


def validate_category(category: str):
    """
    Validate category.
    """

    if not category or not category.strip():
        raise ValueError(
            "category cannot be empty"
        )


# ============================================================
# EXPENSE TOOLS
# ============================================================

@mcp.tool()
def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = "",
):
    """
    Add a new expense entry.

    date must be YYYY-MM-DD.
    amount must be greater than zero.
    """

    validate_date(date)
    validate_amount(amount)
    validate_category(category)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO expenses
                    (
                        date,
                        amount,
                        category,
                        subcategory,
                        note
                    )
                VALUES
                    (%s, %s, %s, %s, %s)
                RETURNING id, date, amount, category,
                          subcategory, note, created_at
                """,
                (
                    date,
                    amount,
                    category,
                    subcategory,
                    note,
                ),
            )

            expense = cur.fetchone()

    logger.info(
        "Expense created | id=%s | amount=%s | category=%s",
        expense["id"],
        amount,
        category,
    )

    return {
        "status": "ok",
        "expense": expense,
    }


@mcp.tool()
def get_expense(expense_id: int):
    """
    Get a single expense by ID.
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note,
                    created_at,
                    updated_at
                FROM expenses
                WHERE id = %s
                  AND deleted_at IS NULL
                """,
                (expense_id,),
            )

            expense = cur.fetchone()

    if not expense:
        return {
            "status": "error",
            "code": "EXPENSE_NOT_FOUND",
            "message": f"Expense {expense_id} does not exist.",
        }

    return {
        "status": "ok",
        "expense": expense,
    }


@mcp.tool()
def list_expenses(
    start_date: str,
    end_date: str,
):
    """
    List active expenses within an inclusive date range.
    """

    validate_date_range(start_date, end_date)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note,
                    created_at,
                    updated_at
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                ORDER BY date ASC, id ASC
                """,
                (
                    start_date,
                    end_date,
                ),
            )

            expenses = cur.fetchall()

    return {
        "status": "ok",
        "count": len(expenses),
        "expenses": expenses,
    }


@mcp.tool()
def update_expense(
    expense_id: int,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None,
):
    """
    Update one or more fields of an existing expense.

    Only fields supplied by the caller are updated.
    """

    if date is not None:
        validate_date(date)

    if amount is not None:
        validate_amount(amount)

    if category is not None:
        validate_category(category)

    updates = []
    params = []

    if date is not None:
        updates.append("date = %s")
        params.append(date)

    if amount is not None:
        updates.append("amount = %s")
        params.append(amount)

    if category is not None:
        updates.append("category = %s")
        params.append(category)

    if subcategory is not None:
        updates.append("subcategory = %s")
        params.append(subcategory)

    if note is not None:
        updates.append("note = %s")
        params.append(note)

    if not updates:
        return {
            "status": "error",
            "code": "NO_FIELDS",
            "message": "At least one field must be provided.",
        }

    updates.append(
        "updated_at = CURRENT_TIMESTAMP"
    )

    query = f"""
        UPDATE expenses
        SET {", ".join(updates)}
        WHERE id = %s
          AND deleted_at IS NULL
        RETURNING
            id,
            date,
            amount,
            category,
            subcategory,
            note,
            created_at,
            updated_at
    """

    params.append(expense_id)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(query, params)

            expense = cur.fetchone()

    if not expense:
        return {
            "status": "error",
            "code": "EXPENSE_NOT_FOUND",
            "message": f"Expense {expense_id} does not exist.",
        }

    logger.info(
        "Expense updated | id=%s",
        expense_id,
    )

    return {
        "status": "ok",
        "expense": expense,
    }


@mcp.tool()
def delete_expense(expense_id: int):
    """
    Soft delete an expense.
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE expenses
                SET deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND deleted_at IS NULL
                RETURNING id
                """,
                (expense_id,),
            )

            deleted = cur.fetchone()

    if not deleted:
        return {
            "status": "error",
            "code": "EXPENSE_NOT_FOUND",
            "message": f"Expense {expense_id} does not exist.",
        }

    logger.info(
        "Expense deleted | id=%s",
        expense_id,
    )

    return {
        "status": "ok",
        "message": f"Expense {expense_id} deleted.",
    }


# ============================================================
# ANALYTICS
# ============================================================

@mcp.tool()
def summarize(
    start_date: str,
    end_date: str,
    category: Optional[str] = None,
):
    """
    Summarize expenses by category within an inclusive date range.
    """

    validate_date_range(start_date, end_date)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            query = """
                SELECT
                    category,
                    SUM(amount) AS total_amount
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
            """

            params = [
                start_date,
                end_date,
            ]

            if category:
                query += " AND category = %s"
                params.append(category)

            query += """
                GROUP BY category
                ORDER BY total_amount DESC
            """

            cur.execute(query, params)

            results = cur.fetchall()

    return {
        "status": "ok",
        "start_date": start_date,
        "end_date": end_date,
        "categories": results,
    }


@mcp.tool()
def monthly_summary(month: str):
    """
    Return total spending and category breakdown for a month.

    month must be YYYY-MM.
    """

    try:
        month_date = datetime.strptime(
            month,
            "%Y-%m"
        ).date()
    except ValueError:
        raise ValueError(
            "month must be in YYYY-MM format"
        )

    start = month_date.replace(day=1)

    if start.month == 12:
        end = start.replace(
            year=start.year + 1,
            month=1
        )
    else:
        end = start.replace(
            month=start.month + 1
        )

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE date >= %s
                  AND date < %s
                  AND deleted_at IS NULL
                """,
                (start, end),
            )

            total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT
                    category,
                    SUM(amount) AS total_amount
                FROM expenses
                WHERE date >= %s
                  AND date < %s
                  AND deleted_at IS NULL
                GROUP BY category
                ORDER BY total_amount DESC
                """,
                (start, end),
            )

            categories = cur.fetchall()

    return {
        "status": "ok",
        "month": month,
        "total": total,
        "categories": categories,
    }


@mcp.tool()
def category_breakdown(
    category: str,
    start_date: str,
    end_date: str,
):
    """
    Return detailed spending information for one category.
    """

    validate_date_range(start_date, end_date)
    validate_category(category)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    COUNT(*) AS transaction_count,
                    COALESCE(SUM(amount), 0) AS total_amount,
                    COALESCE(AVG(amount), 0) AS average_amount,
                    COALESCE(MAX(amount), 0) AS highest_expense
                FROM expenses
                WHERE category = %s
                  AND date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                """,
                (
                    category,
                    start_date,
                    end_date,
                ),
            )

            result = cur.fetchone()

    return {
        "status": "ok",
        "category": category,
        "start_date": start_date,
        "end_date": end_date,
        "summary": result,
    }


@mcp.tool()
def compare_periods(
    first_start_date: str,
    first_end_date: str,
    second_start_date: str,
    second_end_date: str,
):
    """
    Compare spending between two date ranges.
    """

    validate_date_range(
        first_start_date,
        first_end_date
    )

    validate_date_range(
        second_start_date,
        second_end_date
    )

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                """,
                (
                    first_start_date,
                    first_end_date,
                ),
            )

            first_total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                """,
                (
                    second_start_date,
                    second_end_date,
                ),
            )

            second_total = cur.fetchone()["total"]

    first_value = float(first_total)
    second_value = float(second_total)

    difference = second_value - first_value

    percentage_change = None

    if first_value != 0:
        percentage_change = (
            difference / first_value
        ) * 100

    return {
        "status": "ok",
        "first_period": {
            "start": first_start_date,
            "end": first_end_date,
            "total": first_total,
        },
        "second_period": {
            "start": second_start_date,
            "end": second_end_date,
            "total": second_total,
        },
        "difference": difference,
        "percentage_change": percentage_change,
    }


# ============================================================
# BUDGET TOOLS
# ============================================================

@mcp.tool()
def create_budget(
    category: str,
    month: str,
    amount: float,
):
    """
    Create a monthly budget for a category.

    month must be YYYY-MM.
    """

    validate_category(category)
    validate_amount(amount)

    try:
        month_date = datetime.strptime(
            month,
            "%Y-%m"
        ).date()
    except ValueError:
        raise ValueError(
            "month must be in YYYY-MM format"
        )

    month_date = month_date.replace(day=1)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            try:

                cur.execute(
                    """
                    INSERT INTO budgets
                        (
                            category,
                            month,
                            amount
                        )
                    VALUES
                        (%s, %s, %s)
                    RETURNING
                        id,
                        category,
                        month,
                        amount,
                        created_at
                    """,
                    (
                        category,
                        month_date,
                        amount,
                    ),
                )

                budget = cur.fetchone()

            except Exception as exc:

                if "duplicate key" in str(exc).lower():
                    return {
                        "status": "error",
                        "code": "BUDGET_EXISTS",
                        "message": (
                            f"A budget already exists for "
                            f"{category} in {month}."
                        ),
                    }

                raise

    return {
        "status": "ok",
        "budget": budget,
    }


@mcp.tool()
def get_budget(
    category: str,
    month: str,
):
    """
    Get a budget for a category and month.
    """

    validate_category(category)

    try:
        month_date = datetime.strptime(
            month,
            "%Y-%m"
        ).date()
    except ValueError:
        raise ValueError(
            "month must be in YYYY-MM format"
        )

    month_date = month_date.replace(day=1)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    category,
                    month,
                    amount,
                    created_at,
                    updated_at
                FROM budgets
                WHERE category = %s
                  AND month = %s
                """,
                (
                    category,
                    month_date,
                ),
            )

            budget = cur.fetchone()

    if not budget:
        return {
            "status": "error",
            "code": "BUDGET_NOT_FOUND",
            "message": (
                f"No budget exists for "
                f"{category} in {month}."
            ),
        }

    return {
        "status": "ok",
        "budget": budget,
    }


@mcp.tool()
def update_budget(
    budget_id: int,
    amount: float,
):
    """
    Update an existing budget amount.
    """

    validate_amount(amount)

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE budgets
                SET amount = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING
                    id,
                    category,
                    month,
                    amount,
                    updated_at
                """,
                (
                    amount,
                    budget_id,
                ),
            )

            budget = cur.fetchone()

    if not budget:
        return {
            "status": "error",
            "code": "BUDGET_NOT_FOUND",
            "message": (
                f"Budget {budget_id} does not exist."
            ),
        }

    return {
        "status": "ok",
        "budget": budget,
    }


@mcp.tool()
def delete_budget(budget_id: int):
    """
    Delete a budget.
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                DELETE FROM budgets
                WHERE id = %s
                RETURNING id
                """,
                (budget_id,),
            )

            deleted = cur.fetchone()

    if not deleted:
        return {
            "status": "error",
            "code": "BUDGET_NOT_FOUND",
            "message": (
                f"Budget {budget_id} does not exist."
            ),
        }

    return {
        "status": "ok",
        "message": f"Budget {budget_id} deleted.",
    }


@mcp.tool()
def list_budgets(month: Optional[str] = None):
    """
    List budgets.

    If month is supplied, return budgets for that month.
    """

    query = """
        SELECT
            id,
            category,
            month,
            amount,
            created_at,
            updated_at
        FROM budgets
    """

    params = []

    if month:

        try:
            month_date = datetime.strptime(
                month,
                "%Y-%m"
            ).date()
        except ValueError:
            raise ValueError(
                "month must be in YYYY-MM format"
            )

        month_date = month_date.replace(day=1)

        query += " WHERE month = %s"
        params.append(month_date)

    query += """
        ORDER BY month DESC, category ASC
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                query,
                params
            )

            budgets = cur.fetchall()

    return {
        "status": "ok",
        "count": len(budgets),
        "budgets": budgets,
    }


@mcp.tool()
def budget_status(
    category: str,
    month: str,
):
    """
    Return budget utilization for a category and month.
    """

    budget_result = get_budget(
        category,
        month
    )

    if budget_result["status"] != "ok":
        return budget_result

    budget = budget_result["budget"]

    try:
        month_date = datetime.strptime(
            month,
            "%Y-%m"
        ).date()
    except ValueError:
        raise ValueError(
            "month must be in YYYY-MM format"
        )

    start = month_date.replace(day=1)

    if start.month == 12:
        end = start.replace(
            year=start.year + 1,
            month=1
        )
    else:
        end = start.replace(
            month=start.month + 1
        )

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS spent
                FROM expenses
                WHERE category = %s
                  AND date >= %s
                  AND date < %s
                  AND deleted_at IS NULL
                """,
                (
                    category,
                    start,
                    end,
                ),
            )

            spent = cur.fetchone()["spent"]

    budget_amount = float(budget["amount"])
    spent_amount = float(spent)

    remaining = budget_amount - spent_amount

    percentage_used = 0

    if budget_amount > 0:
        percentage_used = (
            spent_amount / budget_amount
        ) * 100

    return {
        "status": "ok",
        "category": category,
        "month": month,
        "budget": budget_amount,
        "spent": spent_amount,
        "remaining": remaining,
        "percentage_used": round(
            percentage_used,
            2
        ),
        "over_budget": spent_amount > budget_amount,
    }


# ============================================================
# SPENDING INSIGHTS
# ============================================================

@mcp.tool()
def spending_insights(
    start_date: str,
    end_date: str,
):
    """
    Generate structured spending insights.

    This tool calculates facts from the database.
    The MCP client/LLM can use these facts to explain
    the spending patterns to the user.
    """

    validate_date_range(
        start_date,
        end_date
    )

    with pool.connection() as conn:
        with conn.cursor() as cur:

            # Total spending
            cur.execute(
                """
                SELECT
                    COUNT(*) AS transaction_count,
                    COALESCE(SUM(amount), 0) AS total,
                    COALESCE(AVG(amount), 0) AS average
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                """,
                (
                    start_date,
                    end_date,
                ),
            )

            overall = cur.fetchone()

            # Category breakdown
            cur.execute(
                """
                SELECT
                    category,
                    SUM(amount) AS total
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                GROUP BY category
                ORDER BY total DESC
                """,
                (
                    start_date,
                    end_date,
                ),
            )

            categories = cur.fetchall()

            # Highest expense
            cur.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note
                FROM expenses
                WHERE date BETWEEN %s AND %s
                  AND deleted_at IS NULL
                ORDER BY amount DESC
                LIMIT 1
                """,
                (
                    start_date,
                    end_date,
                ),
            )

            highest = cur.fetchone()

    return {
        "status": "ok",
        "period": {
            "start": start_date,
            "end": end_date,
        },
        "overall": overall,
        "category_breakdown": categories,
        "highest_expense": highest,
    }


# ============================================================
# RESOURCES
# ============================================================

@mcp.resource(
    "expense://categories",
    mime_type="application/json"
)
def categories():
    """
    Return available expense categories.
    """

    with open(
        CATEGORIES_PATH,
        "r",
        encoding="utf-8"
    ) as f:
        return f.read()


@mcp.resource(
    "expense://recent",
    mime_type="application/json"
)
def recent_expenses():
    """
    Return the 20 most recent active expenses.
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note
                FROM expenses
                WHERE deleted_at IS NULL
                ORDER BY date DESC, id DESC
                LIMIT 20
                """
            )

            expenses = cur.fetchall()

    return json.dumps(
        expenses,
        default=str
    )


@mcp.resource(
    "expense://summary/{month}",
    mime_type="application/json"
)
def monthly_summary_resource(month: str):
    """
    Return monthly spending summary as a resource.
    """

    result = monthly_summary(month)

    return json.dumps(
        result,
        default=str
    )


# ============================================================
# MCP PROMPTS
# ============================================================

@mcp.prompt()
def monthly_spending_review(month: str):
    """
    Generate a reusable prompt for reviewing monthly spending.
    """

    return f"""
Review my spending for {month}.

Use the TrackMyExpense tools/resources to determine:

1. Total spending
2. Spending by category
3. Highest spending category
4. Highest individual expense
5. Budget utilization where budgets exist
6. Categories that deserve attention

Clearly separate factual spending data from your interpretation.
Do not invent expenses or budgets.
"""


@mcp.prompt()
def spending_analysis(
    start_date: str,
    end_date: str,
):
    """
    Generate a reusable spending-analysis prompt.
    """

    return f"""
Analyze my expenses from {start_date} to {end_date}.

Use TrackMyExpense data to identify:

- total spending
- number of transactions
- average transaction amount
- category breakdown
- highest individual expense
- budget utilization where available

Explain the results using only the retrieved data.
"""


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":

    logger.info(
        "Starting TrackMyExpense MCP server..."
    )

    init_db()

    logger.info(
        "TrackMyExpense MCP server started"
    )

    mcp.run(transport="streamable-http")

