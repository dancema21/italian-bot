def sm2_update(easiness_factor: float, interval: int, repetitions: int, quality: int):
    """
    SM-2 algorithm update.
    quality: 5 = correct, 1 = incorrect
    Returns: (new_easiness_factor, new_interval, new_repetitions)
    """
    if quality >= 3:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * easiness_factor)
        new_repetitions = repetitions + 1
    else:
        new_interval = 1
        new_repetitions = 0

    new_ef = easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)

    return new_ef, new_interval, new_repetitions
