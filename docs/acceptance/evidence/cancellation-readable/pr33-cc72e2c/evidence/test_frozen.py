if __name__ == '__main__':
 import hashlib, importlib, json, pathlib, sys
 expected = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
 destination = pathlib.Path(sys.argv[2]); mode = sys.argv[3]
 if mode == 'source': sys.path.insert(0, str(pathlib.Path.cwd() / 'src'))
 base = (pathlib.Path.cwd() / 'src').resolve() if mode == 'source' else pathlib.Path(sys.prefix).resolve()
 def audit():
  result = {}
  for relative, digest in expected.items():
   name = relative.removesuffix('.py').replace('/', '.').removesuffix('.__init__')
   module = importlib.import_module(name); origin = pathlib.Path(module.__file__).resolve()
   assert origin.is_relative_to(base) and hashlib.sha256(origin.read_bytes()).hexdigest() == digest, (name, str(origin))
   result[relative] = {'path': str(origin), 'sha256': digest}
  return result
 before = audit()
 import agentsync, pytest
 assert agentsync.__version__ == '0.3.0a28'
 code = pytest.main(sys.argv[4:])
 after = audit(); assert before == after
 destination.write_text(json.dumps(after, indent=2), encoding='utf-8')
 raise SystemExit(code)
