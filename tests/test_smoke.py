import adaptyv

def test_package_exposes_version():
    assert isinstance(adaptyv.__version__, str) and adaptyv.__version__
