from unittest import TestCase
import mapactionpy_controller.data_search as data_search
from mapactionpy_controller.product_bundle_definition import MapRecipe
import sys
import os
import six

# works differently for python 2.7 and python 3.x
if six.PY2:
    import mock  # noqa: F401
    from mock import mock_open, patch
else:
    from unittest import mock  # noqa: F401
    from unittest.mock import mock_open, patch  # noqa: F401


class TestDataSearch(TestCase):

    def setUp(self):
        self.parent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.cmf_descriptor_path = os.path.join(self.parent_dir, 'example', 'cmf_description_flat_test.json')
        self.recipe_file = os.path.join(self.parent_dir, 'example', 'product_bundle_example.json')
        self.non_existant_file = os.path.join(self.parent_dir, 'example', 'non-existant-file.json')

        # self.ds = data_search.DataSearch(cmf_descriptor_path)

    def test_args(self):
        sys.argv[1:] = ['--cmf', self.cmf_descriptor_path,
                        '--recipe-file', self.recipe_file,
                        '--output-file', 'somefile']
        args = data_search.get_args()
        self.assertEquals(self.cmf_descriptor_path, args.crash_move_folder)
        self.assertEquals(self.recipe_file, args.recipe_file)
        self.assertEquals('somefile', args.output_file)

    def test_non_existant_files_args(self):
        sys.argv[1:] = ['--cmf', self.cmf_descriptor_path,
                        '--recipe-file', self.non_existant_file]

        with self.assertRaises(SystemExit):
            data_search.get_args()

    # @mock.patch('json.dump')
    # @mock.patch('builtins.open', new_callable=mock_open())
    def test_data_search_main(self):
        output_file_for_testing = os.path.join(
            self.parent_dir, 'tests', 'testfiles', 'delete-me-test-output-file.json')

        sys.argv[1:] = ['--cmf', self.cmf_descriptor_path,
                        '--recipe-file', self.recipe_file,
                        '--output-file', output_file_for_testing]

        # check that the output file doesn't already exist. Run the main method and then check that it does exist
        # afterwards.
        if os.path.exists(output_file_for_testing):
            os.remove(output_file_for_testing)

        self.assertFalse(os.path.exists(output_file_for_testing))
        data_search.main()
        self.assertTrue(os.path.exists(output_file_for_testing))

        # In this case we don't expect many changes to the input and output recipes
        # - The data serach to find anything, therefore the no changes to the data_source_path
        # - The data_search regexs should be updated with the country ISO3 code
        # - The changes title remains the same
        # - The number of layers remains the same
        input_recipe = MapRecipe(self.recipe_file)
        output_recipe = MapRecipe(output_file_for_testing)

        print("input {} output {}".format(len(output_recipe.layers), len(input_recipe.layers)))

        self.assertEqual(input_recipe.title, output_recipe.title)
        self.assertEqual(len(output_recipe.layers), len(input_recipe.layers))

        # Finally remove the file so that it isn't present for future tests
        os.remove(output_file_for_testing)
        self.assertFalse(os.path.exists(output_file_for_testing))