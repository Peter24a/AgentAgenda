import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:open_filex/open_filex.dart';

import '../../core/network/api_client.dart';

Future<void> openAgendaDocument(BuildContext context, String route) async {
  final messenger = ScaffoldMessenger.of(context);
  messenger.showSnackBar(const SnackBar(content: Text('Descargando archivo…')));
  try {
    final file = await ApiClient.instance.downloadDocument(route);
    if (!context.mounted) return;
    messenger.hideCurrentSnackBar();
    if (RegExp(
      r'\.(png|jpg|jpeg|webp|gif|bmp)$',
      caseSensitive: false,
    ).hasMatch(file.path)) {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => Dialog(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(
                child: InteractiveViewer(
                  child: Image.file(
                    file,
                    errorBuilder: (_, error, stack) => const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('No se pudo mostrar la imagen.'),
                    ),
                  ),
                ),
              ),
              TextButton(
                onPressed: () async {
                  final result = await OpenFilex.open(file.path);
                  if (result.type != ResultType.done) {
                    messenger.showSnackBar(
                      SnackBar(content: Text(result.message)),
                    );
                  }
                },
                child: const Text('Abrir en otra app'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Cerrar'),
              ),
            ],
          ),
        ),
      );
    } else {
      final result = await OpenFilex.open(file.path);
      if (result.type != ResultType.done) throw Exception(result.message);
    }
  } catch (error) {
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text('$error')));
  }
}

class DocumentLibrary extends StatefulWidget {
  const DocumentLibrary({super.key});
  @override
  State<DocumentLibrary> createState() => _DocumentLibraryState();
}

class _DocumentLibraryState extends State<DocumentLibrary> {
  final _search = TextEditingController();
  final List<Map<String, dynamic>> _documents = [];
  bool _loading = false;
  bool _more = true;
  String? _error;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({bool reset = false}) async {
    final generation = ++_generation;
    setState(() {
      _loading = true;
      _error = null;
      if (reset) _documents.clear();
    });
    try {
      final docs = await ApiClient.instance.listDocuments(
        query: _search.text.trim(),
        offset: _documents.length,
      );
      if (!mounted || generation != _generation) return;
      setState(() {
        _documents.addAll(docs);
        _more = docs.length == 30;
      });
    } catch (error) {
      if (mounted && generation == _generation) {
        setState(() => _error = '$error');
      }
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Mis archivos')),
    body: Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: _search,
            onSubmitted: (_) => _load(reset: true),
            decoration: InputDecoration(
              hintText: 'Buscar por nombre',
              suffixIcon: IconButton(
                tooltip: 'Buscar archivos',
                onPressed: () => _load(reset: true),
                icon: const Icon(Icons.search),
              ),
            ),
          ),
        ),
        if (_loading) const LinearProgressIndicator(),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text(_error!),
                TextButton(
                  onPressed: () => _load(reset: true),
                  child: const Text('Reintentar'),
                ),
              ],
            ),
          ),
        if (!_loading && _error == null && _documents.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Text(
              'No hay archivos que coincidan. Puedes subir uno desde el chat.',
            ),
          ),
        Expanded(
          child: ListView.builder(
            itemCount:
                _documents.length +
                (_more && !_loading && _error == null ? 1 : 0),
            itemBuilder: (context, index) {
              if (index == _documents.length) {
                return TextButton(
                  onPressed: _load,
                  child: const Text('Cargar más'),
                );
              }
              final doc = _documents[index];
              final revisions = doc['revisions'] as List;
              final rev = revisions.isNotEmpty
                  ? revisions.last as Map<String, dynamic>
                  : null;
              final image = (rev?['mime_type'] as String? ?? '').startsWith(
                'image/',
              );
              return ListTile(
                leading: Icon(
                  image ? Icons.image_outlined : Icons.description_outlined,
                ),
                title: Text(doc['title'] as String),
                subtitle: Text(
                  rev == null
                      ? 'Sin archivo'
                      : '${((rev['file_size_bytes'] as num) / 1024).ceil()} KB',
                ),
                trailing: const Icon(Icons.download_outlined),
                onTap: rev == null
                    ? null
                    : () => openAgendaDocument(
                        context,
                        '/v1/documents/${doc['id']}/versions/${rev['version']}/download',
                      ),
              );
            },
          ),
        ),
      ],
    ),
  );
}

Future<PlatformFile?> pickAgendaFile({required bool photos}) async {
  final result = await FilePicker.platform.pickFiles(
    type: photos ? FileType.image : FileType.any,
    allowMultiple: false,
    withData: false,
    withReadStream: true,
  );
  return result?.files.single;
}
