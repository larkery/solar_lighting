from math import tanh

BRIGHTNESS_K = "brightness_k"
BRIGHTNESS_X = "brightness_x"
BRIGHTNESS_MIN = "brightness_min"
BRIGHTNESS_MAX = "brightness_max"

COLOUR_K = "colour_k"
COLOUR_X = "colour_x"
COLOUR_MIN = "colour_min"
COLOUR_MAX = "colour_max"

def _evaluate(now, sunrise, noon, sunset, k, x, minimum, maximum):
    if now < noon:
        x = (1+tanh(k*(now - (sunrise + x))))/2
    else:
        x = (1+tanh(k*(sunset - (now + x))))/2
    return minimum + (maximum - minimum) * x

def brightness_and_colour(now, sunrise, noon, sunset, parameters):
    """
    Now, sunrise, noon, sunset are all in floating-point hours
    parameters has the control parameters
    returns (brightness, colour)
    """
    brightness_k = parameters.get(BRIGHTNESS_K, 1.0)
    brightness_x = parameters.get(BRIGHTNESS_X, 0.0)
    brightness_min = parameters.get(BRIGHTNESS_MIN, 5)
    brightness_max = parameters.get(BRIGHTNESS_MAX, 100)
    
    colour_k = parameters.get(COLOUR_K, 0.5)
    colour_x = parameters.get(COLOUR_X, 0.5)
    colour_min = parameters.get(COLOUR_MIN, 2000)
    colour_max = parameters.get(COLOUR_MAX, 2500)

    brightness = _evaluate(now, sunrise, noon, sunset,
                           brightness_k, brightness_x,
                           brightness_min, brightness_max)

    colour = _evaluate(now, sunrise, noon, sunset,
                       colour_k, colour_x,
                       colour_min, colour_max)

    return (brightness, colour)
