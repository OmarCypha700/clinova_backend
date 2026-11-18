"""Grade boundaries, shared by the Grades page, its exports and maintenance commands."""


def grade_for(percentage):
    """Grade for an overall percentage (0–100). 0% means nothing scored yet."""
    if percentage == 0:
        return "N/A"
    if percentage >= 80:
        return "Distinction"
    if percentage >= 70:
        return "Credit"
    if percentage >= 60:
        return "Pass"
    return "Fail"


def percentage(score, maximum):
    """Rounded like the Grades page: one decimal place, 0 when there's no maximum."""
    return round(score / maximum * 100, 1) if maximum > 0 else 0.0
