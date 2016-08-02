import fnmatch
import os
import shutil
import stat

def copytree(src, dst, symlinks=False, ignore=None):
    """
    This is a contributed re-implementation of 'copytree' that
    should work with the exact same behavior on multiple platforms.

    """

    if not os.path.exists(dst):
        os.makedirs(dst)
        shutil.copystat(src, dst)
    lst = os.listdir(src)

    if ignore:
        excl = ignore(src, lst)
        lst = [x for x in lst if x not in excl]

    for item in lst:
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if symlinks and os.path.islink(s):
            if os.path.lexists(d):
                os.remove(d)
            os.symlink(os.readlink(s), d)
            try:
                st = os.lstat(s)
                mode = stat.S_IMODE(st.st_mode)
                os.lchmod(d, mode)
            except:
                pass  # lchmod not available
        elif os.path.isdir(s):
            copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)

def detect_django_settings():
    """
    Automatically try to discover Django settings files,
    return them as relative module paths.
    """

    matches = []
    for root, dirnames, filenames in os.walk(os.getcwd()):
        for filename in fnmatch.filter(filenames, '*settings.py'):
            full = os.path.join(root, filename)
            if 'site-packages' in full:
                continue
            full = os.path.join(root, filename)
            package_path = full.replace(os.getcwd(), '')
            package_module = package_path.replace(os.sep, '.').split('.', 1)[1].replace('.py', '')

            matches.append(package_module)
    return matches

def detect_flask_apps():
    """
    Automatically try to discover Flask apps files,
    return them as relative module paths.
    """

    matches = []
    for root, dirnames, filenames in os.walk(os.getcwd()):
        for filename in fnmatch.filter(filenames, '*.py'):
            full = os.path.join(root, filename)
            if 'site-packages' in full:
                continue

            full = os.path.join(root, filename)

            with open(full, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    app = None

                    # Kind of janky..
                    if '= Flask(' in line:
                        app = line.split('= Flask(')[0].strip()
                    if '=Flask(' in line:
                        app = line.split('=Flask(')[0].strip()

                    if not app:
                        continue

                    package_path = full.replace(os.getcwd(), '')
                    package_module = package_path.replace(os.sep, '.').split('.', 1)[1].replace('.py', '')
                    app_module = package_module + '.' + app

                    matches.append(app_module)

    return matches

def add_event_source(event_source, lambda_arn, target_function, boto_session):
    """

    Given an event_source dictionary item, a session and a lambda_arn,
    hack into Kappa's Gibson, create out an object we can call
    to schedule this event, and add the event source.

    """
    import kappa.function
    import kappa.restapi
    import kappa.event_source.dynamodb_stream
    import kappa.event_source.kinesis
    import kappa.event_source.s3
    import kappa.event_source.sns
    import kappa.event_source.cloudwatch
    import kappa.policy
    import kappa.role
    import kappa.awsclient

    class PseudoContext(object):
        def __init__(self):
            return

    class PseudoFunction(object):
        def __init__(self):
            return

    event_source_map = {
        'dynamodb': kappa.event_source.dynamodb_stream.DynamoDBStreamEventSource,
        'kinesis': kappa.event_source.kinesis.KinesisEventSource,
        's3': kappa.event_source.s3.S3EventSource,
        'sns': kappa.event_source.sns.SNSEventSource,
        'events': kappa.event_source.cloudwatch.CloudWatchEventSource
    }

    arn = event_source['arn']
    events = event_source['events']
    _, _, svc, _ = arn.split(':', 3)

    event_source_func = event_source_map.get(svc, None)
    if not event_source_func:
        raise ValueError('Unknown event source: {0}'.format(arn))
    
    def autoreturn(self, function_name):
        return function_name

    event_source_func._make_notification_id = autoreturn

    ctx = PseudoContext()
    ctx.session = boto_session

    split_arn = lambda_arn.split(':')
    arn_front = ':'.join(split_arn[:-1])
    arn_back = split_arn[-1]
    ctx.environment = arn_back

    funk = PseudoFunction()
    funk.name = target_function
    funk.arn = arn_front
    funk._context = ctx

    event_source_obj = event_source_func(ctx, event_source)
    rule_response = event_source_obj.add(funk)
    return rule_response
