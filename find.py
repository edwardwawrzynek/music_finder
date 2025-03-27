#! /usr/bin/env python3

import subprocess
import time
import os
import re
import discogs_client
import music_tag
import argparse
from yt_dlp import YoutubeDL

d_client = discogs_client.Client('MusicFinder/0.1', user_token='qcaPDIVYeLReeGdsiXlKzmBlvuaEJEWGivecoQeT')

# tag all files in the current directory
def tag(artist, album, year, artwork):
    # walk all the files in the directory
    files = [file for file in os.listdir() if file.endswith("m4a")]
    num_files = len(files)

    for file in files:
        # get the index of the track in the album
        file_index = int(file.split('-')[0])
        # get the rest of the album title from the file name
        file_title = '-'.join(file.removesuffix('.m4a').split('-')[1:])

        # remove common suffixes from title)
        file_title = re.sub(r'(\s*(\(|\[)(Dir|dir|official|Official|Live|Lyric|Music|Demo|Audio|feat|Closed-|((19|20)\d\d))[^\)]*(\)|\])\s*)+', "", file_title)
        
        # replace some common unicode characters
        file_title = file_title.replace("？", "?")
        file_title = file_title.replace("＂", "\"")
        file_title = file_title.replace("’", "'")
        file_title = file_title.replace("–", "-")

        # remove artist from beginning of title (if present)
        file_title = re.sub(r'\s*' + artist + '\s*-\s*', '', file_title)

        # remove space surrounding title
        file_title = re.sub(r'\s*(.*)\s*', r'\1', file_title)

        # remove quotes surrounding title (if present)
        file_title = re.sub(r'\"\s*(.*)\s*\"', r'\1', file_title)
        file_title = re.sub(r'＂\s*(.*)\s*＂', r'\1', file_title)

        # Tag file
        f = music_tag.load_file(file)

        f['title'] = file_title
        f['album'] = album
        f['artist'] = artist
        f['year'] = year
        f['totaltracks'] = num_files
        f['tracknumber'] = file_index
        f['artwork'] = artwork

        print("Tagging: " + file_title + ", " + album + ", " + artist + ", " + str(year) + ", " + str(file_index) + "/" + str(num_files))

        f.save()

# Find an album by name and artist
def find_album(yt_playlist, album, artist, music_dir, skip_dir_setup, skip_prompt, vfmt):
    results = d_client.search(album, type='release', artist=artist)
    if results.pages == 0 or len(results) == 0:
        print("ERROR: Cannot find album")
        exit(1)
    
    res = results[0]

    album_artist = res.artists[0].name
    album_title = res.title
    year = res.year
    img_url = res.images[0]['uri']

    # Search for just CD releases. If we find one with the same album, artist, and year as the top result, use it's art instead.
    # Discogg tends to have better album art for CD releases
    results_cd = d_client.search(album, type='release', artist=artist, format='CD')
    if len(results_cd) > 0:
        count = 0
        for res_cd in results_cd:
            count += 1
            if res_cd.artists[0].name.lower() == album_artist.lower() and res_cd.title.lower() == album_title.lower() and res_cd.year == year and res_cd.images and len(res_cd.images) > 0:
                img_url = res_cd.images[0]['uri']
                break
            
            if count > 30:
                break

    print()
    print("Found release: " + album_title + ", " + album_artist + ", " + str(year))

    if not skip_prompt:
        proceed = input("Proceed [Y/n]? ")

        if proceed.startswith("n") or proceed.startswith("N"):
            print("STOPPING")
            exit(0)
    
    if not skip_dir_setup:
        # create directory for artist and album
        artist_path = music_dir + "/" + artist.replace(" ", "_")

        if not os.path.exists(artist_path):
            os.makedirs(artist_path)
        os.chdir(artist_path)

        if not os.path.exists(album):
            os.makedirs(album)
        os.chdir(album)
    
    download(yt_playlist, vfmt)
    
    # download artwork
    path = "COVER_ART.png"
    download_res = subprocess.run(['wget', '-O', path, img_url]).returncode

    if download_res != 0:
        print("ERROR: Cannot download album artwork")
        exit(1)
    
    with open(path, 'rb') as img_file:
        tag(album_artist, album_title, year, img_file.read())
    
    os.remove(path)

# youtube download format
YT_FORMAT = "249"

# download the given youtube playlist
def download(yt_playlist, vfmt):
    # download
    result = subprocess.run(["yt-dlp", "-o", "%(playlist_index)s-%(title)s.%(ext)s", "-f", vfmt, "https://www.youtube.com/watch?list=" + yt_playlist]).returncode

    if result != 0:
        print("ERROR: download failed")
        exit(result)
    
    # convert any webm to m4a
    files = next(os.walk('.'), (None, None, []))[2]
    for file in files:
        if file.endswith(".webm") or file.endswith(".mp4"):
            result = subprocess.run(["ffmpeg", "-i", file, "-b:a", "48k", "-vn", file.removesuffix(".webm") + ".m4a"]).returncode

            if result != 0:
                print("ERROR: webm -> m4a conversion failed")
                exit(result)
            # remove webm file
            os.remove(file)

# Identify the artist and album from a youtube playlist
def extract_album(yt_playlist):
    # get video info from ydl
    ydl = YoutubeDL({'playlist_items': '1', 'quiet': True})
    info = ydl.extract_info('https://www.youtube.com/watch?list=' + yt_playlist, download=False)
    info = ydl.sanitize_info(info)
    # extract album artist & title
    title = info['title']
    artist = info['entries'][0]['uploader']
    return title, artist


def run(yt_playlist, album, artist, music_dir, skip_dir_setup, skip_prompt, vfmt):
    find_album(yt_playlist, album, artist, music_dir, skip_dir_setup, skip_prompt, vfmt)

parser = argparse.ArgumentParser(prog='music_find', description='Find Music')
parser.add_argument('yt_playlist')
parser.add_argument('--album')
parser.add_argument('--artist')
parser.add_argument('--use_current_dir', action='store_true')
parser.add_argument('--music_dir', default='/home/edward/Music/')
parser.add_argument('--yes', action='store_true')
parser.add_argument('--yt_fmt', default=YT_FORMAT)

args = parser.parse_args()

# if full url was given, extract playlist
if "list=" in args.yt_playlist:
    args.yt_playlist = args.yt_playlist.split("list=")[1]

# if album or artist was not given, try to get it from album
if args.artist == None or args.album == None:
    e_album, e_artist = extract_album(args.yt_playlist)

    if args.album == None:
        if not args.yes:
            print()
            use_album = input("Use album: " + e_album + " [Y/n]? ")
            if use_album.startswith("n") or use_album.startswith("N"):
                args.album = input("Album name: ")
            else:
                args.album = e_album
        else:        
            args.album = e_album

    if args.artist == None:
        if not args.yes:
            print()
            use_artist = input("Use artist: " + e_artist + " [Y/n]? ")
            if use_artist.startswith("n") or use_artist.startswith("N"):
                args.artist = input("Artist name: ")
            else:
                args.artist = e_artist
        else:    
            args.artist = e_artist

run(args.yt_playlist, args.album, args.artist, args.music_dir, args.use_current_dir, args.yes, args.yt_fmt)
