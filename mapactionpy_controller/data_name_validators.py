import csv
import mapactionpy_controller as mac
import six


# abstract class
# Done using the "old-school" methed described here, without using the abs module
# https://stackoverflow.com/a/25300153
class DataNameClause:
    def __init__(self):
        if self.__class__ is DataNameClause:
            raise NotImplementedError(
                'DataNameClause is an abstract class and cannot be instantiated directly')

    def validate(self, clause_value):
        if self.__class__ is DataNameClause:
            raise NotImplementedError(
                'DataNameClause is an abstract class and the `validate` method cannot be called directly')


class DataNameFreeTextClause(DataNameClause):
    def __init__(self):
        pass

    def validate(self, clause_value):
        return True if clause_value is None else clause_value


class DataNameLookupClause(DataNameClause):
    def __init__(self, clause_name, csv_path, lookup_field):
        self.known_values = {}

        if six.PY2:
            with open(csv_path, 'rb') as csv_file:
                self._init_known_values(csv_path, csv_file, lookup_field)
        else:
            with open(csv_path, 'r', newline='', encoding='iso-8859-1') as csv_file:
                self._init_known_values(csv_path, csv_file, lookup_field)

    def _init_known_values(self, csv_path, csv_file, lookup_field):
        self.filename = csv_path
        csv_reader = csv.DictReader(
            csv_file, delimiter=',', quotechar='"')
        if lookup_field in csv_reader.fieldnames:
            self.lookup_field = lookup_field
        else:
            raise mac.data_name_convention.DataNameException(
                'invalid validation lookup_field primary key {} in file {}'.format(lookup_field, csv_path))

        for row in csv_reader:
            pk = row[lookup_field]
            non_lookup_keys = [x for x in row.keys() if x != lookup_field]
            self.known_values[pk] = {n: row[n] for n in non_lookup_keys}

    def validate(self, clause_value):
        if clause_value in self.known_values:
            return self.known_values[clause_value]
        else:
            return None