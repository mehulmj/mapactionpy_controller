import logging
import os
import glob
import re
import hashlib

import jsonschema

import mapactionpy_controller.data_schemas as data_schemas
import mapactionpy_controller.state_serialization as state_serialization
from mapactionpy_controller import _get_validator_for_config_schema
import mapactionpy_controller.task_renderer as task_renderer


logger = logging.getLogger(__name__)
validate_against_layer_schema = _get_validator_for_config_schema('layer_properties-v0.2.schema')


class FixMissingGISDataTask(task_renderer.TaskReferralBase):
    _task_template_filename = 'missing-gis-file'
    _primary_key_template = 'Could not find data for "{{<%layer.name%>}}"'

    def __init__(self, recipe_lyr, cmf):
        super(FixMissingGISDataTask, self).__init__()
        self.context_data.update(task_renderer.layer_adapter(recipe_lyr))
        self.context_data.update(task_renderer.cmf_description_adapter(cmf))


class FixMultipleMatchingFilesTask(task_renderer.TaskReferralBase):
    _task_template_filename = 'multiple-matching-files'
    _primary_key_template = 'More than one dataset available for "{{<%layer.name%>}}"'

    def __init__(self, recipe_lyr, cmf, datasources_list):
        super(FixMultipleMatchingFilesTask, self).__init__()
        self.context_data.update(task_renderer.layer_adapter(recipe_lyr))
        self.context_data.update(task_renderer.cmf_description_adapter(cmf))
        # Roll-our-own one-line adapter here:
        self.context_data.update({
            'datasources_list': [{'datasources': datasources} for datasources in sorted(datasources_list)]
        })


class LabelClass:
    """
    Enables selection of properties to support labels in a Layer
    """

    def __init__(self, row):
        self.class_name = row["class_name"]
        self.expression = row["expression"]
        self.sql_query = row["sql_query"]
        self.show_class_labels = row["show_class_labels"]

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Overrides the default implementation (unnecessary in Python 3)"""
        return not self.__eq__(other)


class RecipeLayer:

    OPTIONAL_FIELDS = ('data_source_path', 'data_name', 'data_schema', 'data_source_checksum',
                       'layer_file_checksum', 'extent', 'use_for_frame_extent')

    def __init__(self, layer_def, lyr_props, verify_on_creation=True):
        """Constructor.  Creates an instance of layer properties

        Arguments:
            row {dict} -- From the layerProperties.json file
        """
        validate_against_layer_schema(layer_def)

        # Required fields
        self.name = layer_def["name"]
        self.reg_exp = layer_def["reg_exp"]
        self.definition_query = layer_def["definition_query"]
        self.schema_definition = layer_def["schema_definition"]

        self.display = layer_def["display"]
        self.add_to_legend = layer_def["add_to_legend"]
        self.label_classes = list()
        for lbl_class_def in layer_def["label_classes"]:
            self.label_classes.append(LabelClass(lbl_class_def))

        self._get_layer_file_path(layer_def, lyr_props, verify_on_creation)

        # Optional fields
        self._get_data_schema(layer_def, lyr_props)
        self.layer_file_checksum = layer_def.get('layer_file_checksum', self._calc_layer_file_checksum())
        self.data_source_path = layer_def.get('data_source_path', None)
        if self.data_source_path:
            self.data_source_path = os.path.abspath(self.data_source_path)

        self.data_source_checksum = layer_def.get('data_source_checksum', self._calc_data_source_checksum())
        self.data_name = layer_def.get('data_name', None)
        self.extent = layer_def.get('extent', None)
        self.use_for_frame_extent = layer_def.get('use_for_frame_extent', None)

    def _get_layer_file_path(self, layer_def, lyr_props, verify_on_creation):
        if 'layer_file_path' in layer_def:
            self.layer_file_path = os.path.abspath(layer_def['layer_file_path'])
            if verify_on_creation:
                self.verify_layer_file_path()

        else:
            self.layer_file_path = os.path.abspath(os.path.join(
                lyr_props.cmf.layer_rendering,
                (self.name + lyr_props.extension)
            ))

    def _get_data_schema(self, layer_def, lyr_props):
        if 'data_schema' in layer_def:
            self.data_schema = layer_def['data_schema']
        else:
            schema_file = os.path.abspath(os.path.join(lyr_props.cmf.data_schemas, self.schema_definition))
            self.data_schema = data_schemas.parse_yaml(schema_file)

        # check that the schema itself is valid.
        jsonschema.Draft7Validator.check_schema(self.data_schema)

    def verify_layer_file_path(self):
        if not os.path.exists(self.layer_file_path):
            raise ValueError("The expected layer file {} could not be found."
                             "".format(self.layer_file_path))

    def _check_lyr_is_in_recipe(self, recipe):
        # This is being paraniod. This can only occur if there are more than one MapRecipe objects
        # being proceed simulatiously. There is isn't currently a use case where that would occur in
        # production code. This check is present just in case.
        if self not in recipe.all_layers():
            error_msg = 'Attempting to update a layer ("{}") which is not part of the recipe'.format(
                self.name)
            logging.error(error_msg)
            raise ValueError(error_msg)

    def get_data_finder(self, cmf, all_gis_files):
        """
        This method returns a function which tests for the existance of data that matches
        the param `recipe_lyr.reg_exp`.

        Create a new function for each layer within a recipe.
        """
        # Get list of files, so that they are only queried on disk once.
        # Make this into a list of full_paths (as returned by `get_all_gisfiles(cmf)`) and
        # just the file name
        # all_gis_files = [(f_path, os.path.basename(f_path)) for f_path in get_all_gisfiles(cmf)]

        def _data_finder(**kwargs):
            recipe = kwargs['state']

            self._check_lyr_is_in_recipe(recipe)

            found_files = []

            # Match filename *including extension* against regex
            # But only store the filename without extension
            found_files.extend(
                [(f_path, os.path.splitext(f_name)[0])
                 for f_path, f_name in all_gis_files if re.match(self.reg_exp, f_name)]
            )

            # Do checks and raise exceptions if required.
            self._check_found_files(found_files, cmf)

            # else assume everthing is OK:
            self.data_source_path, self.data_name = found_files.pop()
            self.data_source_checksum = self._calc_data_source_checksum()

            return recipe

        return _data_finder

    def _check_found_files(self, found_files, cmf):
        """
        This method checks the list of files in `get_lyr_data_finder`. It is called within `get_lyr_data_finder`
        so there is no need to call it seperately. A 'ValueError' exception, along with a Task and task
        description will be raised if there are too few or too many files in the `found_files` list.

        @param found_files: A list of tuples. Each tuple should be represent one of the files found and the tuple
                            should be in the format `(full_path, filename_without_extension)`
        @param recipe_lyr: The recipe being processed. Used for providing contact to any error message that may
                        be created.
        @param cmf: The crash move folder being searched. Used for providing contact to any error message that
                    may be created.
        @raises ValueError: If there is not exactly one file in the found_files lilst.
        """
        # If no data matching is found:
        # Test on list of paths as they are guarenteed to be unique, whereas base filenames are not
        if not found_files:
            missing_data_task = FixMissingGISDataTask(self, cmf)
            raise ValueError(missing_data_task)

        # If multiple matching files are found
        if len(found_files) > 1:
            found_datasources = [f_path for f_path, f_name in found_files]
            multiple_files_task = FixMultipleMatchingFilesTask(self, cmf, found_datasources)
            raise ValueError(multiple_files_task)

    def _calc_data_source_checksum(self):

        def files_in_shp_file():
            base_path = os.path.splitext(self.data_source_path)
            files = glob.glob('{}*'.format(base_path))
            return [f_path for f_path in files if (os.path.isfile(f_path) and f_path.endswith('.lock'))]

        def files_in_dir():
            return [os.path.join(f_path, f_name) for f_path, d_name, f_name in os.walk(self.data_source_path)]

        if not self.data_source_path:
            return None

        f_list = []

        if (os.path.isfile(self.data_source_path)):
            f_list = files_in_shp_file()
        elif (os.path.isdir(self.data_source_path)):
            f_list = files_in_dir()

        hash = hashlib.md5()
        for f_path in sorted(f_list):
            hash.update(open(f_path, "rb").read())

        return hash.hexdigest()

    def _calc_layer_file_checksum(self):
        if not os.path.isfile(self.layer_file_path):
            return None

        hash = hashlib.md5()
        hash.update(open(self.layer_file_path, "rb").read())
        return hash.hexdigest()

    def get_schema_checker(self, runner):
        def _schema_checker(**kwargs):
            if not self.data_source_path:
                raise ValueError(
                    'Cannot check data schema until relevant data has been found.'
                    ' Please use `get_data_finder()` first.')
            recipe = kwargs['state']
            self._check_lyr_is_in_recipe(recipe)
            runner.check_data_schema(self)

        return _schema_checker

    def get_extents_calc(self, runner):
        def _extents_calc(**kwargs):
            print('layer._extents_calc')
            if not self.data_source_path:
                print('Have no self.data_source_path')
                raise ValueError(
                    'Cannot calculate bounding box until relevant data has been found.'
                    ' Please use `get_data_finder()` first.')

            print('Has self.data_source_path')
            recipe = kwargs['state']
            self._check_lyr_is_in_recipe(recipe)
            print('passed _check_lyr_is_in_recipe')
            runner.get_lyr_extents(self)
            return recipe

        return _extents_calc

    def __eq__(self, other):
        try:
            return self.__dict__ == other.__dict__
        except AttributeError:
            return False

    def __ne__(self, other):
        """Overrides the default implementation (unnecessary in Python 3)"""
        return not self.__eq__(other)

    def __getstate__(self):
        return state_serialization.get_state_optional_fields(self, RecipeLayer.OPTIONAL_FIELDS)

    def __setstate__(self, state):
        state_serialization.set_state_optional_fields(self, state, RecipeLayer.OPTIONAL_FIELDS)