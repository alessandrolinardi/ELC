"""CSV report generation for unmatched labels."""
import io
import csv


def generate_csv_report(match_report) -> str:
    """Generate CSV report of unmatched labels."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Pagina Originale", "Tracking Estratto", "Corriere", "Motivo"])

    for result in match_report.unmatched:
        tracking = result.tracking if result.tracking else "(non estratto)"
        carrier = result.carrier if result.carrier else "-"
        reason = result.unmatched_reason.value if result.unmatched_reason else "Sconosciuto"
        writer.writerow([result.page_number, tracking, carrier, reason])

    return output.getvalue()
