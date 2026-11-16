FROM nginx:alpine

# Копируем уже готовую папку dist в Nginx
COPY dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]