<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tri des fichiers media</title>
    <link rel="stylesheet" href="./styles.css">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script> <!-- Inclure jQuery -->
</head>
<body>
    <h1>Tri des fichiers media</h1>

    <form id="fileForm" method="POST" enctype="multipart/form-data">
        <label for="source">Dossier source :</label>
        <input type="text" id="source" name="source" required>

        <label for="dest_images">Dossier images :</label>
        <input type="text" id="dest_images" name="dest_images" required>

        <label for="dest_videos">Dossier vidéos :</label>
        <input type="text" id="dest_videos" name="dest_videos" required>

        <label for="dest_others">Dossier autres :</label>
        <input type="text" id="dest_others" name="dest_others" required>

        <label for="action">Action :</label>
        <select name="action" id="action">
            <option value="move">Déplacer</option>
            <option value="copy">Copier</option>
        </select>

        <label for="subdirs">Inclure sous-dossiers :</label>
        <input type="checkbox" id="subdirs" name="subdirs" checked>

        <button type="submit">Traiter</button>
    </form>

    <div id="resultReport" style="display:none;">
        <h2>Rapport de traitement des fichiers</h2>
        <table id="fileReportTable">
            <thead>
                <tr>
                    <th>Nom Original</th>
                    <th>Nouvel emplacement</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    </div>

    <script>
        $(document).ready(function() {
            // Écouter la soumission du formulaire
            $('#fileForm').submit(function(e) {
                e.preventDefault(); // Empêcher la soumission normale du formulaire

                // Utiliser AJAX pour envoyer les données
                $.ajax({
                    url: 'process.php', // Le script PHP de traitement
                    type: 'POST',
                    data: $(this).serialize(), // Sérialiser les données du formulaire
                    success: function(response) {
                        // Analyser la réponse du serveur
                        var result = JSON.parse(response);

                        // Afficher le rapport
                        $('#resultReport').show();
                        $('#fileReportTable tbody').empty(); // Vider la table avant d'ajouter les nouvelles lignes

                        result.files.forEach(function(file) {
                            $('#fileReportTable tbody').append(
                                `<tr>
                                    <td>${file.original}</td>
                                    <td><a href="file://${file.new}" target="_blank">${file.new}</a></td>
                                </tr>`
                            );
                        });
                    },
                    error: function(xhr, status, error) {
                        alert('Une erreur est survenue lors du traitement.');
                    }
                });
            });
        });
    </script>
</body>
</html>
