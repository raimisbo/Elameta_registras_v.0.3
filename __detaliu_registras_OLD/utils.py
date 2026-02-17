import csv
from io import TextIOWrapper

def import_csv(file):
    preview = []
    errors_exist = False

    decoded_file = TextIOWrapper(file, encoding='utf-8-sig', newline='')

    try:
        reader = csv.DictReader(decoded_file)

        for row in reader:
            row_data = {}
            errors = {}

            for key, value in row.items():
                row_data[key] = value.strip() if isinstance(value, str) else value

                if not value:
                    errors[key] = "Reikšmė privaloma"

            row_data['errors'] = errors
            if errors:
                errors_exist = True

            preview.append(row_data)

    except csv.Error as e:
        return {
            'preview': [],
            'errors_exist': True,
            'csv_error': str(e),
        }

    return {
        'preview': preview,
        'errors_exist': errors_exist,
        'csv_error': None,
    }