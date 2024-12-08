<?php
// Fonction pour obtenir la date à partir du nom du fichier ou de ses métadonnées
function get_file_date($filepath, $filename) {
    // Regex pour capturer les différents formats d'images et de vidéos avec les préfixes IMG, VID ou PANO
    $date_regex = '/((IMG|VID|PANO)[-_])?(\d{4})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})/';  // Format IMG-YYYYMMDD-HHMMSS
    $alt_date_regex1 = '/((IMG|VID|PANO)[-_])?(\d{8})(\d{6})/'; // Format IMG-YYYYMMDD-HHMMSS
    $alt_date_regex2 = '/((IMG|VID|PANO)[-_])?(\d{8})([-_].*)?(\.([a-zA-Z0-9]+))?$/'; // Format IMG-YYYYMMDD-(du texte)-HHMMSS
    $alt_date_regex3 = '/((IMG|VID|PANO)[-_])?(\d{8})([-_](\w+)(\d+))?(\.([a-zA-Z0-9]+))?$/'; // Format IMG-YYYYMMDD-(du texte suivi de chiffres)

    $date_matches = [];

    // Initialiser les variables de date
    $year = $month = $day = $hour = $minute = $second = "";
    $formatted_name = "";
    $full_date = "";

    // Tester les différentes expressions régulières
    if (preg_match($date_regex, $filename, $date_matches)) {
        // Format classique IMG-YYYY_MM_DD-HH_MM_SS
        $year = $date_matches[3];
        $month = $date_matches[4];
        $day = $date_matches[5];
        $hour = $date_matches[6];
        $minute = $date_matches[7];
        $second = $date_matches[8];
    } elseif (preg_match($alt_date_regex1, $filename, $date_matches)) {
        // Format IMG-YYYYMMDD-HHMMSS
        $year = substr($date_matches[3], 0, 4);
        $month = substr($date_matches[3], 4, 2);
        $day = substr($date_matches[3], 6, 2);
        $hour = substr($date_matches[4], 0, 2);
        $minute = substr($date_matches[4], 2, 2);
        $second = substr($date_matches[4], 4, 2);
    } elseif (preg_match($alt_date_regex2, $filename, $date_matches)) {
        // Format IMG-YYYYMMDD-(du texte)-HHMMSS
        $year = substr($date_matches[3], 0, 4);
        $month = substr($date_matches[3], 4, 2);
        $day = substr($date_matches[3], 6, 2);
        $hour = substr($date_matches[4], 0, 2);
        $minute = substr($date_matches[4], 2, 2);
        $second = substr($date_matches[4], 4, 2);
    } elseif (preg_match($alt_date_regex3, $filename, $date_matches)) {
        // Format IMG-YYYYMMDD-(du texte suivi de chiffres)
        $year = substr($date_matches[3], 0, 4);
        $month = substr($date_matches[3], 4, 2);
        $day = substr($date_matches[3], 6, 2);
        // Heure actuelle si l'heure n'est pas fournie dans le nom du fichier
        $hour = date('H');
        $minute = date('i');
        $second = date('s');
    } else {
        // Si aucune date n'est trouvée, on prend la date du fichier
        $file_time = filemtime($filepath);
        $year = date('Y', $file_time);
        $month = date('m', $file_time);
        $day = date('d', $file_time);
        $hour = date('H', $file_time);
        $minute = date('i', $file_time);
        $second = date('s', $file_time);
    }

    // Construire le nom formaté et la date complète
    $separationSign = "_";
    $formatted_name = "$year$separationSign$month$separationSign$day-$hour$separationSign$minute$separationSign$second";
    $full_date = "$year/$month/$day";  // Date correcte sous le format YYYY/MM/DD

    return [
        'year' => $year,
        'month' => $month,
        'day' => $day,
        'formatted_name' => $formatted_name,
        'full_date' => $full_date
    ];
}

// Fonction pour déterminer où déplacer/copier un fichier
function determine_destination($file, $dest_images, $dest_videos, $dest_others, $subfolder_path, $image_extensions, $video_extensions) {
    $extension = strtolower($file->getExtension());

    // Si c'est une image
    if (in_array($extension, $image_extensions)) {
        return $dest_images;
    }
    // Si c'est une vidéo
    if (in_array($extension, $video_extensions)) {
        return $dest_videos;
    }
    // Sinon, c'est un autre type de fichier
    return $dest_others;
}

// Fonction pour vérifier l'unicité du nom de fichier
function get_unique_filename($path, $filename) {
    $counter = 1;
    $new_filename = $filename;
    while (file_exists($path . DIRECTORY_SEPARATOR . $new_filename)) {
        $new_filename = preg_replace('/(\.\w+)$/', "($counter)\\1", $filename); // Ajouter (2), (3), etc.
        $counter++;
    }
    return $new_filename;
}

// Fonction principale pour traiter les fichiers
function process_files($source, $dest_images, $dest_videos, $dest_others, $action, $include_subdirs) {
    // Extensions pour catégorisation
    $image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'];
    $video_extensions = ['mp4', 'mkv', 'mov', 'avi', 'flv', 'wmv'];

    $iterator = $include_subdirs ? new RecursiveIteratorIterator(new RecursiveDirectoryIterator($source)) 
                                 : new DirectoryIterator($source);

    $processed_files = []; // Tableau pour stocker les fichiers traités

    foreach ($iterator as $file) {
        if ($file->isFile()) {
            $filepath = $file->getPathname();
            $filename = $file->getFilename();

            // Récupérer la date du fichier
            $file_date = get_file_date($filepath, $filename);

            // Créer les sous-dossiers nécessaires
            $subfolder_path = $file_date['year'] . DIRECTORY_SEPARATOR . $file_date['month'] . DIRECTORY_SEPARATOR . $file_date['day'];
            $destination = determine_destination($file, $dest_images, $dest_videos, $dest_others, $subfolder_path, $image_extensions, $video_extensions);

            // Assurer que le chemin final existe
            $final_path = $destination . DIRECTORY_SEPARATOR . $subfolder_path;
            if (!is_dir($final_path)) {
                mkdir($final_path, 0777, true); // Crée tous les sous-dossiers nécessaires
            }

            // Renommer le fichier et vérifier les conflits
            $new_filename = $file_date['formatted_name'] . '.' . $file->getExtension();
            $new_filename = get_unique_filename($final_path, $new_filename);

            // Déplacer ou copier le fichier
            $final_path_with_file = $final_path . DIRECTORY_SEPARATOR . $new_filename;
            if ($action === 'move') {
                rename($filepath, $final_path_with_file);
            } else {
                copy($filepath, $final_path_with_file);
            }

            // Ajouter le fichier traité au rapport
            $processed_files[] = [
                'original' => $filename,
                'new' => $final_path_with_file
            ];
        }
    }

    return $processed_files; // Retourner le tableau des fichiers traités
}

// Traitement des données envoyées par le formulaire
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $source = $_POST['source'];
    $dest_images = $_POST['dest_images'];
    $dest_videos = $_POST['dest_videos'];
    $dest_others = $_POST['dest_others'];
    $action = $_POST['action'];  // 'move' ou 'copy'
    $include_subdirs = isset($_POST['include_subdirs']) ? true : false;

    // Appel de la fonction pour traiter les fichiers
    $processed_files = process_files($source, $dest_images, $dest_videos, $dest_others, $action, $include_subdirs);

    // Affichage du rapport des fichiers traités
    echo "<h3>Rapport de traitement</h3>";
    echo "<ul>";
    foreach ($processed_files as $file) {
        echo "<li><a href='file://{$file['new']}' target='_blank'>{$file['original']} -> {$file['new']}</a></li>";
    }
    echo "</ul>";
}

header('Content-Type: application/json');
echo json_encode($report);
?>
