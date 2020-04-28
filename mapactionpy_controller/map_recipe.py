from mapactionpy_controller.label_class import LabelClass
from mapactionpy_controller import _get_validator_for_schema

validate_against_atlas_schema = _get_validator_for_schema('atlas-v0.2.schema')
validate_against_layer_schema = _get_validator_for_schema('layer_properties-v0.2.schema')
validate_against_recipe_schema = _get_validator_for_schema('map-recipe-v0.2.schema')


class RecipeLayer:
    def __init__(self, layer_def):
        """Constructor.  Creates an instance of layer properties

        Arguments:
            row {dict} -- From the layerProperties.json file
        """
        validate_against_layer_schema(layer_def)

        self.layerName = layer_def["LayerName"]
        self.regExp = layer_def["RegExp"]
        self.definitionQuery = layer_def["DefinitionQuery"]
        self.display = layer_def["Display"]
        self.addToLegend = layer_def["AddToLegend"]
        self.labelClasses = list()
        for labelClass in layer_def["LabelClasses"]:
            self.labelClasses.append(LabelClass(labelClass))


class RecipeFrame:
    def __init__(self, frame_def, lyr_props):
        # Required fields
        self.name = frame_def["name"]
        # TODO Parse layers properly
        self.layers = self._parse_layers(frame_def["layers"], lyr_props)
        # self.layers = frame_def["layers"]

        # Optional fields
        self.scale_text_element = frame_def.get('scale_text_element', None)
        self.scale_text_element = frame_def.get('spatial_ref_text_element', None)

    def _parse_layers(self, lyrs_def, lyr_props):
        lyrs = {}
        for lyr_def in lyrs_def:
            # if lyr_def only includes the name of the layer and no other properties
            # then import them from a LayerProperties object
            # Else, load them from the lyr_def
            l_name = lyr_def['name']
            if len(lyr_def) == 1:
                lyrs[l_name] = lyr_props.properties.get(l_name, l_name)
            else:
                lyrs[l_name] = RecipeLayer(lyrs_def)

        return lyrs


class RecipeAtlas:
    def __init__(self, atlas_def, recipe):
        validate_against_atlas_schema(atlas_def)

        # Required fields
        self.map_frame = atlas_def[""]
        self.layer_name = atlas_def[""]
        self.column_name = atlas_def[""]

        try:
            lyrs = recipe.map_frames[self.map_frame]
            lyr = lyrs[self.layer_name]
            # TODO add a check that the named column is in the layer
        except KeyError as ke:
            raise ValueError(ke)


class MapRecipe:
    """
    MapRecipe - Ordered list of layers for each Map Product
    """

    def __init__(self, recipe_def, lyr_props):
        validate_against_recipe_schema(recipe_def)

        # Required fields
        self.mapnumber = recipe_def["mapnumber"]
        self.category = recipe_def["category"]
        self.export = recipe_def["export"]
        self.product = recipe_def["product"]
        self.map_frames = self._parse_map_frames(recipe_def["map_frames"], lyr_props)
        self.summary = recipe_def["summary"]

        # Optional fields
        self.runners = recipe_def.get('runners', None)
        atlas_def = recipe_def.get('atlas', None)
        if atlas_def:
            self.atlas = RecipeAtlas(atlas_def, self)
        else:
            self.atlas = None

    def _parse_map_frames(self, map_frames_def, lyr_props):
        map_frames = {}
        for frame_def in map_frames_def:
            mf = RecipeFrame(frame_def, lyr_props)
            map_frames[mf.name] = mf

        return map_frames

    def _do_something_to_check_scale_text_element_etc(self):
        # TODO
        pass
