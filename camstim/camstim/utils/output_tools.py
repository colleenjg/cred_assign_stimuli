"""
"""
import pickle

import yaml


def dict2types(input_dict):
    """ Converts a dictionary into a matching dictionary
            of just its types.
    """
    output_dict = {}
    for k, v in input_dict.items():
        if isinstance(v, dict):
            output_dict[k] = dict2types(v)
        elif isinstance(v, (list, tuple)):
            if len(v) > 20:
                output_dict[k] = list2types(v[:20])
            else:
                output_dict[k] = list2types(v)
        else:
            output_dict[k] = item2typestr(v)
    return output_dict

def list2types(input_list):
    """ Converts a list into a matching list
            of just its types
    """
    output_list = []
    for item in input_list:
        if isinstance(item, dict):
            output_list.append(dict2types(item))
        elif isinstance(item, (list, tuple)):
            output_list.append(list2types(item))
        else:
            output_list.append(item2typestr(item))
    return output_list

def item2typestr(item):
    typestr = str(type(item))
    return typestr.lstrip("<type '").rstrip("'>").replace("NoneType", "None")
    

def output2types(path):
    """ Converts an output file to a type dict.
    """
    with open(path, 'rb') as f:
        data = pickle.load(f)
    return dict2types(data)


def main():
    path = r"C:\Users\derricw\camstim\output\180215141113.pkl"
    type_dict = output2types(path)
    with open("test.yaml", 'w') as f:
        yaml.dump(type_dict, f)

if __name__ == '__main__':
    main()
